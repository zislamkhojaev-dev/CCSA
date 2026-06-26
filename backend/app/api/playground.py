import asyncio
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.core.deps import get_current_user
from app.database import get_db
from app.models import PlaygroundFile, PlaygroundJob, User
from app.schemas.common import MessageOut
from app.schemas.playground import PlaygroundFileOut, PlaygroundJobCreate, PlaygroundJobOut
from app.services.redis_events import subscribe_playground_events
from app.services.storage import storage_service

router = APIRouter()


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


@router.post("/jobs", response_model=PlaygroundJobOut)
async def create_job(
    body: PlaygroundJobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = PlaygroundJob(
        user_id=user.id,
        scenario_id=body.scenario_id,
        use_scenario_prompt=body.use_scenario_prompt,
        custom_prompt=body.custom_prompt,
        status="pending",
    )
    db.add(job)
    await db.flush()
    return PlaygroundJobOut(id=job.id, status=job.status, scenario_id=job.scenario_id, created_at=job.created_at, files=[])


@router.post("/jobs/{job_id}/upload")
async def upload_files(
    job_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(PlaygroundJob).where(PlaygroundJob.id == job_id, PlaygroundJob.user_id == user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    for upload in files:
        data = await upload.read()
        key = storage_service.upload_bytes(data, "playground", upload.filename or "audio.mp3")
        pf = PlaygroundFile(job_id=job.id, filename=upload.filename or "audio.mp3", storage_key=key, status="queued")
        db.add(pf)
    job.status = "pending"
    await db.flush()
    return {"message": f"Uploaded {len(files)} file(s)", "queued": len(files)}


@router.post("/jobs/{job_id}/run", response_model=MessageOut)
async def run_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from worker.asr_limit import reset_asr_slots
    from worker.tasks.playground import process_playground_file
    from app.services.settings_store import get_bool_setting

    reset_asr_slots()

    result = await db.execute(
        select(PlaygroundJob)
        .where(PlaygroundJob.id == job_id, PlaygroundJob.user_id == user.id)
        .options(selectinload(PlaygroundJob.files))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for pf in job.files:
        if pf.status == "transcribing":
            pf.status = "queued"
            pf.error_message = None

    queued = [f for f in job.files if f.status in ("queued", "error")]
    if not queued:
        if any(f.status == "analyzing" for f in job.files):
            raise HTTPException(
                status_code=400,
                detail="Анализ уже выполняется — дождитесь завершения (ASR может занять несколько минут)",
            )
        raise HTTPException(status_code=400, detail="Нет файлов для анализа. Загрузите аудио (.mp3 / .wav).")
    job.status = "processing"
    for pf in queued:
        if pf.status == "error":
            pf.status = "queued"
            pf.error_message = None
    await db.flush()

    sequential = await get_bool_setting(db, "playground_sequential", True)
    if sequential:
        first = min(queued, key=lambda f: f.id)
        process_playground_file.delay(first.id)
    else:
        for pf in queued:
            process_playground_file.delay(pf.id)
    return MessageOut(message=f"Запущен анализ {len(queued)} файл(ов)")


@router.get("/jobs/{job_id}", response_model=PlaygroundJobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(PlaygroundJob)
        .where(PlaygroundJob.id == job_id, PlaygroundJob.user_id == user.id)
        .options(selectinload(PlaygroundJob.files).selectinload(PlaygroundFile.result))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return PlaygroundJobOut(
        id=job.id,
        status=job.status,
        scenario_id=job.scenario_id,
        created_at=job.created_at,
        files=[_file_out(f) for f in job.files],
    )


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: int, user: User = Depends(get_current_user)):
    async def generator():
        pubsub = subscribe_playground_events(job_id)
        try:
            while True:
                message = await asyncio.to_thread(pubsub.get_message, timeout=30.0)
                if message and message["type"] == "message":
                    yield {"event": "status", "data": message["data"]}
                    data = json.loads(message["data"])
                    if data.get("done"):
                        break
                else:
                    yield {"event": "ping", "data": "{}"}
        finally:
            pubsub.unsubscribe()

    return EventSourceResponse(generator())


@router.get("/files/{file_id}/audio")
async def stream_playground_audio(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PlaygroundFile)
        .where(PlaygroundFile.id == file_id)
        .options(selectinload(PlaygroundFile.job))
    )
    pf = result.scalar_one_or_none()
    if not pf or pf.job.user_id != user.id or not pf.storage_key:
        raise HTTPException(status_code=404, detail="Audio not found")
    data = storage_service.download_bytes(pf.storage_key)
    return Response(
        content=data,
        media_type=storage_service.media_type_for_key(pf.storage_key),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/files/{file_id}/promote-to-calls", response_model=MessageOut)
async def promote_to_calls(
    file_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    from worker.tasks.playground import promote_playground_file

    result = await db.execute(
        select(PlaygroundFile)
        .where(PlaygroundFile.id == file_id)
        .options(selectinload(PlaygroundFile.job), selectinload(PlaygroundFile.result))
    )
    pf = result.scalar_one_or_none()
    if not pf or pf.job.user_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    if pf.status != "ready":
        raise HTTPException(status_code=400, detail="File not ready")
    call_id = promote_playground_file(pf.id)
    return MessageOut(message=f"Promoted to call #{call_id}")


@router.post("/jobs/{job_id}/promote-to-calls", response_model=MessageOut)
async def promote_job_to_calls(
    job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    from worker.tasks.playground import promote_playground_job

    result = await db.execute(
        select(PlaygroundJob)
        .where(PlaygroundJob.id == job_id, PlaygroundJob.user_id == user.id)
        .options(selectinload(PlaygroundJob.files).selectinload(PlaygroundFile.result))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    ready_count = sum(1 for f in job.files if f.status == "ready" and f.result)
    if ready_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Нет готовых файлов для сохранения. Дождитесь завершения анализа.",
        )
    try:
        call_ids = promote_playground_job(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return MessageOut(message=f"Сохранено в общую базу: {len(call_ids)} звонок(ов)")
