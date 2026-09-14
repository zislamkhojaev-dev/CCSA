from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, ErrorCode, USER_ERROR_STORAGE
from app.core.logging import log_error
from app.models import (
    AnalysisResult,
    Call,
    CallExportJob,
    CallTag,
    SupervisorNote,
    Tag,
    Transcription,
    User,
)
from app.ports import StoragePort
from app.schemas.calls import (
    CallDetailOut,
    CallExportJobOut,
    CallListItem,
    CallStatusOut,
    NoteOut,
)
from app.schemas.common import Paginated
from app.schemas.tags import TagOut
from app.services.call_query import build_calls_count_query, build_calls_list_query
from app.services.call_utils import duration_seconds_from_utterances
from app.services.calls_export import (
    CALLS_EXPORT_MAX_ROWS,
    CALLS_EXPORT_SYNC_MAX_IDS,
    count_export_rows_async,
    fetch_export_rows_async,
)
from app.services.storage import storage_service
from app.services.task_dispatch import task_dispatcher
from worker.task_lock import is_locked
import logging

logger = logging.getLogger(__name__)


def parse_date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    try:
        if len(raw) == 10:
            dt = datetime.fromisoformat(raw)
            if end_of_day:
                return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            return dt
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class CallService:
    def __init__(self, storage: StoragePort | None = None) -> None:
        self._storage = storage or storage_service

    async def list_calls(self, db: AsyncSession, *, page: int, page_size: int, **filter_kw) -> Paginated[CallListItem]:
        total = await db.scalar(build_calls_count_query(**filter_kw)) or 0
        q = build_calls_list_query(**filter_kw)
        result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
        calls = result.scalars().unique().all()

        call_ids = [c.id for c in calls]
        scores: dict[int, int | None] = {}
        if call_ids:
            ar_rows = await db.execute(
                select(AnalysisResult.call_id, AnalysisResult.total_score, AnalysisResult.created_at)
                .where(AnalysisResult.call_id.in_(call_ids))
                .order_by(AnalysisResult.call_id, AnalysisResult.created_at.desc())
            )
            for call_id, total_score, _created in ar_rows.all():
                if call_id not in scores:
                    scores[call_id] = total_score

        missing_duration_ids = [c.id for c in calls if c.duration is None]
        duration_from_trans: dict[int, int] = {}
        if missing_duration_ids:
            latest = (
                select(
                    Transcription.call_id,
                    Transcription.utterances,
                    func.row_number()
                    .over(
                        partition_by=Transcription.call_id,
                        order_by=(Transcription.created_at.desc(), Transcription.id.desc()),
                    )
                    .label("rn"),
                ).where(Transcription.call_id.in_(missing_duration_ids))
            ).subquery()
            tr_rows = await db.execute(select(latest.c.call_id, latest.c.utterances).where(latest.c.rn == 1))
            for call_id, utterances in tr_rows.all():
                dur = duration_seconds_from_utterances(utterances)
                if dur is not None:
                    duration_from_trans[call_id] = dur

        items = [
            CallListItem(
                id=c.id,
                call_uuid=c.call_uuid,
                operator_name=c.operator.full_name if c.operator else None,
                direction=c.direction,
                duration=c.duration if c.duration is not None else duration_from_trans.get(c.id),
                client_number=c.client_number,
                call_timestamp=c.call_timestamp or c.created_at,
                status=c.status,
                total_score=scores.get(c.id),
                is_violation=None,
            )
            for c in calls
        ]
        return Paginated(items=items, total=total, page=page, page_size=page_size)

    async def bulk_delete(self, db: AsyncSession, ids: list[int]) -> int:
        if not ids:
            raise AppError.invalid("No call ids provided")
        result = await db.execute(select(Call).where(Call.id.in_(ids)))
        calls = result.scalars().all()
        if not calls:
            raise AppError.not_found("Calls not found")
        for call in calls:
            await db.delete(call)
        return len(calls)

    async def export_sync_rows(self, db: AsyncSession, ids: list[int]):
        if len(ids) > CALLS_EXPORT_SYNC_MAX_IDS:
            raise AppError.invalid(
                f"Слишком много звонков для мгновенного экспорта (макс. {CALLS_EXPORT_SYNC_MAX_IDS})"
            )
        rows = await fetch_export_rows_async(db, ids=ids)
        if not rows:
            raise AppError.not_found("Звонки не найдены")
        return rows

    async def create_export_job(self, db: AsyncSession, user: User, body) -> CallExportJobOut:
        total = await count_export_rows_async(db, body.filters)
        if total == 0:
            raise AppError.invalid("По выбранным фильтрам звонков нет")
        if total > CALLS_EXPORT_MAX_ROWS:
            raise AppError.invalid(
                f"Слишком много звонков ({total}). Сузьте фильтры (лимит {CALLS_EXPORT_MAX_ROWS})"
            )
        job = CallExportJob(
            user_id=user.id,
            format=body.format,
            filters_json=body.filters.model_dump(),
            status="pending",
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)
        await db.commit()
        task_dispatcher.run_calls_export(job.id)
        return CallExportJobOut(
            id=job.id,
            format=job.format,
            status=job.status,
            message="Задача на экспорт создана",
            row_count=0,
            created_at=job.created_at,
        )

    async def get_owned_export_job(self, db: AsyncSession, job_id: int, user: User) -> CallExportJob:
        job = await db.get(CallExportJob, job_id)
        if not job or job.user_id != user.id:
            raise AppError.not_found("Задача экспорта не найдена")
        return job

    def export_job_out(self, job: CallExportJob) -> CallExportJobOut:
        return CallExportJobOut(
            id=job.id,
            format=job.format,
            status=job.status,
            message=None,
            row_count=job.row_count,
            error_message=job.error_message,
            created_at=job.created_at,
            finished_at=job.finished_at,
        )

    def download_export_bytes(self, job: CallExportJob) -> bytes:
        if job.status != "completed" or not job.storage_path:
            raise AppError(ErrorCode.JOB_NOT_READY, "Файл экспорта ещё не готов", 400)
        try:
            return self._storage.download_bytes(job.storage_path)
        except AppError:
            raise
        except Exception as e:
            log_error(logger, "Export download failed", method="download_export_bytes", params={"job_id": job.id}, exc=e)
            raise AppError(ErrorCode.EXT_STORAGE_UNAVAILABLE, USER_ERROR_STORAGE, 500) from e

    async def get_status(self, db: AsyncSession, call_id: int) -> CallStatusOut:
        call = await db.get(Call, call_id)
        if not call:
            raise AppError.not_found("Call not found")
        return CallStatusOut(id=call.id, status=call.status, error_message=call.error_message)

    async def get_detail(self, db: AsyncSession, call_id: int) -> CallDetailOut:
        result = await db.execute(
            select(Call)
            .where(Call.id == call_id)
            .options(
                selectinload(Call.operator),
                selectinload(Call.scenario),
                selectinload(Call.tags).selectinload(CallTag.tag),
                selectinload(Call.notes).selectinload(SupervisorNote.user),
            )
        )
        call = result.scalar_one_or_none()
        if not call:
            raise AppError.not_found("Call not found")

        latest_trans = (
            await db.execute(
                select(Transcription)
                .where(Transcription.call_id == call_id)
                .order_by(Transcription.created_at.desc(), Transcription.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        latest_analysis = (
            await db.execute(
                select(AnalysisResult)
                .where(AnalysisResult.call_id == call_id)
                .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        audio_url = f"/api/v1/calls/{call.id}/audio" if call.audio_path else None
        notes = [
            NoteOut(id=n.id, text=n.text, user_name=n.user.full_name, created_at=n.created_at) for n in call.notes
        ]
        duration = call.duration
        if duration is None and latest_trans:
            duration = duration_seconds_from_utterances(latest_trans.utterances)
        return CallDetailOut(
            id=call.id,
            call_uuid=call.call_uuid,
            operator_id=call.operator_id,
            operator_name=call.operator.full_name if call.operator else None,
            scenario_id=call.scenario_id,
            scenario_name=call.scenario.name if call.scenario else None,
            direction=call.direction,
            duration=duration,
            client_number=call.client_number,
            call_timestamp=call.call_timestamp or call.created_at,
            status=call.status,
            error_message=call.error_message,
            audio_url=audio_url,
            tags=[TagOut(id=ct.tag.id, name=ct.tag.name) for ct in call.tags],
            transcriptions=[latest_trans] if latest_trans else [],
            analysis_results=[latest_analysis] if latest_analysis else [],
            notes=notes,
        )

    async def get_audio_path(self, db: AsyncSession, call_id: int) -> str:
        result = await db.execute(select(Call).where(Call.id == call_id))
        call = result.scalar_one_or_none()
        if not call or not call.audio_path:
            raise AppError.not_found("Audio not found")
        return call.audio_path

    async def reanalyze(self, db: AsyncSession, call_id: int, scenario_id: int | None) -> None:
        result = await db.execute(select(Call).where(Call.id == call_id))
        call = result.scalar_one_or_none()
        if not call:
            raise AppError.not_found("Call not found")
        if is_locked("analyze", call_id) or is_locked("transcribe", call_id):
            raise AppError.conflict("Звонок уже обрабатывается", ErrorCode.JOB_IN_PROGRESS)
        call.status = "analyzing"
        call.error_message = None
        await db.commit()
        task_dispatcher.reanalyze_call(call_id, scenario_id)

    async def retranscribe(self, db: AsyncSession, call_id: int) -> None:
        result = await db.execute(select(Call).where(Call.id == call_id))
        call = result.scalar_one_or_none()
        if not call:
            raise AppError.not_found("Call not found")
        if not call.audio_path:
            raise AppError.invalid("Call has no audio file")
        if is_locked("analyze", call_id) or is_locked("transcribe", call_id):
            raise AppError.conflict("Звонок уже обрабатывается — дождитесь завершения", ErrorCode.JOB_IN_PROGRESS)
        call.status = "transcribing"
        call.error_message = None
        await db.commit()
        task_dispatcher.retranscribe_call(call_id)

    async def update_tags(self, db: AsyncSession, call_id: int, tag_ids: list[int]) -> None:
        result = await db.execute(select(Call).where(Call.id == call_id))
        call = result.scalar_one_or_none()
        if not call:
            raise AppError.not_found("Call not found")
        await db.execute(CallTag.__table__.delete().where(CallTag.call_id == call_id))
        if tag_ids:
            existing = await db.execute(select(Tag.id).where(Tag.id.in_(tag_ids)))
            valid_ids = {row[0] for row in existing.all()}
            unknown = set(tag_ids) - valid_ids
            if unknown:
                raise AppError.invalid(f"Unknown tag ids: {sorted(unknown)}")
            for tag_id in tag_ids:
                db.add(CallTag(call_id=call_id, tag_id=tag_id))

    async def add_note(self, db: AsyncSession, call_id: int, user: User, text: str) -> NoteOut:
        result = await db.execute(select(Call).where(Call.id == call_id))
        if not result.scalar_one_or_none():
            raise AppError.not_found("Call not found")
        note = SupervisorNote(call_id=call_id, user_id=user.id, text=text)
        db.add(note)
        await db.flush()
        return NoteOut(id=note.id, text=note.text, user_name=user.full_name, created_at=note.created_at)


call_service = CallService()
