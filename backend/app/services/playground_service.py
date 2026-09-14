from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.models import PlaygroundFile, PlaygroundJob, User
from app.ports import StoragePort
from app.schemas.playground import PlaygroundFileOut, PlaygroundJobCreate, PlaygroundJobOut
from app.services.settings_store import get_bool_setting
from app.services.storage import storage_service
from app.services.task_dispatch import task_dispatcher
from worker.asr_limit import reset_asr_slots
from worker.tasks.playground import promote_playground_file, promote_playground_job


def _file_out(f: PlaygroundFile) -> PlaygroundFileOut:
    trans = analysis = None
    if f.result:
        trans = f.result.transcription
        analysis = f.result.analysis
    audio_url = f"/api/v1/playground/files/{f.id}/audio" if f.storage_key else None
    return PlaygroundFileOut(
        id=f.id,
        filename=f.filename,
        status=f.status,
        error_message=f.error_message,
        audio_url=audio_url,
        transcription=trans,
        analysis=analysis,
    )


class PlaygroundService:
    def __init__(self, storage: StoragePort | None = None) -> None:
        self._storage = storage or storage_service

    async def _owned_job(self, db: AsyncSession, job_id: int, user: User) -> PlaygroundJob:
        result = await db.execute(
            select(PlaygroundJob).where(PlaygroundJob.id == job_id, PlaygroundJob.user_id == user.id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise AppError.not_found("Job not found")
        return job

    async def create_job(self, db: AsyncSession, user: User, body: PlaygroundJobCreate) -> PlaygroundJobOut:
        job = PlaygroundJob(
            user_id=user.id,
            scenario_id=body.scenario_id,
            use_scenario_prompt=body.use_scenario_prompt,
            custom_prompt=body.custom_prompt,
            status="pending",
        )
        db.add(job)
        await db.flush()
        return PlaygroundJobOut(
            id=job.id, status=job.status, scenario_id=job.scenario_id, created_at=job.created_at, files=[]
        )

    async def upload_files(self, db: AsyncSession, job_id: int, user: User, files: list[tuple[str, bytes]]) -> int:
        job = await self._owned_job(db, job_id, user)
        for filename, data in files:
            key = self._storage.upload_bytes(data, "playground", filename or "audio.mp3")
            db.add(PlaygroundFile(job_id=job.id, filename=filename or "audio.mp3", storage_key=key, status="queued"))
        job.status = "pending"
        await db.flush()
        return len(files)

    async def run_job(self, db: AsyncSession, job_id: int, user: User) -> int:
        reset_asr_slots()
        result = await db.execute(
            select(PlaygroundJob)
            .where(PlaygroundJob.id == job_id, PlaygroundJob.user_id == user.id)
            .options(selectinload(PlaygroundJob.files))
        )
        job = result.scalar_one_or_none()
        if not job:
            raise AppError.not_found("Job not found")
        for pf in job.files:
            if pf.status == "transcribing":
                pf.status = "queued"
                pf.error_message = None
        queued = [f for f in job.files if f.status in ("queued", "error")]
        if not queued:
            if any(f.status == "analyzing" for f in job.files):
                raise AppError.invalid(
                    "Анализ уже выполняется — дождитесь завершения (ASR может занять несколько минут)"
                )
            raise AppError.invalid("Нет файлов для анализа. Загрузите аудио (.mp3 / .wav).")
        job.status = "processing"
        for pf in queued:
            if pf.status == "error":
                pf.status = "queued"
                pf.error_message = None
        await db.flush()
        sequential = await get_bool_setting(db, "playground_sequential", True)
        await db.commit()
        if sequential:
            first = min(queued, key=lambda f: f.id)
            task_dispatcher.process_playground_file(first.id)
        else:
            for pf in queued:
                task_dispatcher.process_playground_file(pf.id)
        return len(queued)

    async def get_job(self, db: AsyncSession, job_id: int, user: User) -> PlaygroundJobOut:
        result = await db.execute(
            select(PlaygroundJob)
            .where(PlaygroundJob.id == job_id, PlaygroundJob.user_id == user.id)
            .options(selectinload(PlaygroundJob.files).selectinload(PlaygroundFile.result))
        )
        job = result.scalar_one_or_none()
        if not job:
            raise AppError.not_found("Job not found")
        return PlaygroundJobOut(
            id=job.id,
            status=job.status,
            scenario_id=job.scenario_id,
            created_at=job.created_at,
            files=[_file_out(f) for f in job.files],
        )

    async def assert_job_owner(self, db: AsyncSession, job_id: int, user: User) -> None:
        await self._owned_job(db, job_id, user)

    async def audio_path(self, db: AsyncSession, file_id: int, user: User) -> str:
        result = await db.execute(
            select(PlaygroundFile)
            .where(PlaygroundFile.id == file_id)
            .options(selectinload(PlaygroundFile.job))
        )
        pf = result.scalar_one_or_none()
        if not pf or pf.job.user_id != user.id or not pf.storage_key:
            raise AppError.not_found("Audio not found")
        return pf.storage_key

    async def promote_file(self, db: AsyncSession, file_id: int, user: User) -> int:
        result = await db.execute(
            select(PlaygroundFile)
            .where(PlaygroundFile.id == file_id)
            .options(selectinload(PlaygroundFile.job), selectinload(PlaygroundFile.result))
        )
        pf = result.scalar_one_or_none()
        if not pf or pf.job.user_id != user.id:
            raise AppError.not_found("File not found")
        if pf.status != "ready":
            raise AppError.invalid("File not ready")
        return promote_playground_file(pf.id)

    async def promote_job(self, db: AsyncSession, job_id: int, user: User) -> list[int]:
        result = await db.execute(
            select(PlaygroundJob)
            .where(PlaygroundJob.id == job_id, PlaygroundJob.user_id == user.id)
            .options(selectinload(PlaygroundJob.files).selectinload(PlaygroundFile.result))
        )
        job = result.scalar_one_or_none()
        if not job:
            raise AppError.not_found("Job not found")
        ready_count = sum(1 for f in job.files if f.status == "ready" and f.result)
        if ready_count == 0:
            raise AppError.invalid("Нет готовых файлов для сохранения. Дождитесь завершения анализа.")
        try:
            return promote_playground_job(job_id)
        except ValueError as e:
            raise AppError.invalid("Не удалось сохранить файлы в общую базу") from e


playground_service = PlaygroundService()
