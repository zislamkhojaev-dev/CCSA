import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.core.deps import get_current_user
from app.database import get_db
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
from app.schemas.calls import (
    CallBulkDelete,
    CallDetailOut,
    CallExportJobCreate,
    CallExportJobOut,
    CallExportSyncBody,
    CallListItem,
    CallTagsUpdate,
    NoteCreate,
    NoteOut,
)
from app.schemas.tags import TagOut
from app.schemas.common import MessageOut, Paginated
from app.services.call_query import build_calls_count_query, build_calls_list_query
from app.services.call_utils import duration_seconds_from_utterances
from app.services.calls_export import (
    CALLS_EXPORT_MAX_ROWS,
    CALLS_EXPORT_SYNC_MAX_IDS,
    count_export_rows_async,
    encode_export_file,
    fetch_export_rows_async,
)
from app.services.redis_events import subscribe_call_export_events
from app.services.storage import storage_service

router = APIRouter()


def _parse_date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
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


@router.get("", response_model=Paginated[CallListItem])
async def list_calls(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = None,
    operator_match: str | None = Query(None, pattern="^(eq|contains)$"),
    operator_value: str | None = None,
    client_match: str | None = Query(None, pattern="^(eq|contains)$"),
    client_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    duration_op: str | None = Query(None, pattern="^(eq|lt|gt)$"),
    duration_value: int | None = None,
    score_op: str | None = Query(None, pattern="^(eq|lt|gt)$"),
    score_value: int | None = None,
    tag_id: int | None = None,
    sort_by: str = Query("call_timestamp"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    dt_from = _parse_date(date_from)
    dt_to = _parse_date(date_to, end_of_day=True)

    filter_kw = dict(
        status_filter=status_filter or None,
        operator_match=operator_match,
        operator_value=operator_value,
        client_match=client_match,
        client_value=client_value,
        date_from=dt_from,
        date_to=dt_to,
        duration_op=duration_op,
        duration_value=duration_value,
        score_op=score_op,
        score_value=score_value,
        tag_id=tag_id,
    )

    total = await db.scalar(build_calls_count_query(**filter_kw)) or 0
    q = build_calls_list_query(**filter_kw, sort_by=sort_by, sort_order=sort_order)
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
        tr_rows = await db.execute(
            select(Transcription.call_id, Transcription.utterances).where(
                Transcription.call_id.in_(missing_duration_ids)
            )
        )
        for call_id, utterances in tr_rows.all():
            dur = duration_seconds_from_utterances(utterances)
            if dur is not None:
                duration_from_trans[call_id] = dur

    items = []
    for c in calls:
        score = scores.get(c.id)
        items.append(
            CallListItem(
                id=c.id,
                call_uuid=c.call_uuid,
                operator_name=c.operator.full_name if c.operator else None,
                direction=c.direction,
                duration=c.duration if c.duration is not None else duration_from_trans.get(c.id),
                client_number=c.client_number,
                call_timestamp=c.call_timestamp or c.created_at,
                status=c.status,
                total_score=score,
                is_violation=None,
            )
        )
    return Paginated(items=items, total=total, page=page, page_size=page_size)


@router.post("/bulk-delete", response_model=MessageOut)
async def bulk_delete_calls(
    body: CallBulkDelete,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not body.ids:
        raise HTTPException(status_code=400, detail="No call ids provided")
    result = await db.execute(select(Call).where(Call.id.in_(body.ids)))
    calls = result.scalars().all()
    if not calls:
        raise HTTPException(status_code=404, detail="Calls not found")
    for call in calls:
        await db.delete(call)
    await db.commit()
    return MessageOut(message=f"Deleted {len(calls)} call(s)")


@router.post("/export")
async def export_calls_sync(
    body: CallExportSyncBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Synchronous export of selected call ids (immediate download)."""
    if len(body.ids) > CALLS_EXPORT_SYNC_MAX_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Слишком много звонков для мгновенного экспорта (макс. {CALLS_EXPORT_SYNC_MAX_IDS})",
        )
    rows = await fetch_export_rows_async(db, ids=body.ids)
    if not rows:
        raise HTTPException(status_code=404, detail="Звонки не найдены")
    content, media_type, filename = encode_export_file(rows, body.format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/jobs", response_model=CallExportJobOut)
async def create_call_export_job(
    body: CallExportJobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Queue an async export for calls matching filters."""
    total = await count_export_rows_async(db, body.filters)
    if total == 0:
        raise HTTPException(status_code=400, detail="По выбранным фильтрам звонков нет")
    if total > CALLS_EXPORT_MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Слишком много звонков ({total}). Сузьте фильтры "
                f"(лимит {CALLS_EXPORT_MAX_ROWS})"
            ),
        )

    job = CallExportJob(
        user_id=user.id,
        format=body.format,
        filters_json=body.filters.model_dump(),
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from worker.tasks.calls_export import run_calls_export

    run_calls_export.delay(job.id)
    return CallExportJobOut(
        id=job.id,
        format=job.format,
        status=job.status,
        message="Задача на экспорт создана",
        row_count=0,
        created_at=job.created_at,
    )


async def _get_owned_export_job(db: AsyncSession, job_id: int, user: User) -> CallExportJob:
    job = await db.get(CallExportJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Задача экспорта не найдена")
    return job


@router.get("/export/jobs/{job_id}", response_model=CallExportJobOut)
async def get_call_export_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await _get_owned_export_job(db, job_id, user)
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


@router.get("/export/jobs/{job_id}/events")
async def call_export_job_events(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_export_job(db, job_id, user)

    async def generator():
        pubsub = subscribe_call_export_events(job_id)
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


@router.get("/export/jobs/{job_id}/download")
async def download_call_export_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await _get_owned_export_job(db, job_id, user)
    if job.status != "completed" or not job.storage_path:
        raise HTTPException(status_code=400, detail="Файл экспорта ещё не готов")
    try:
        content = storage_service.download_bytes(job.storage_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось прочитать файл: {e}") from e

    ext = "csv" if job.format == "csv" else "json"
    media = "text/csv; charset=utf-8" if ext == "csv" else "application/json; charset=utf-8"
    filename = f"calls-export-{job.id}.{ext}"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{call_id}", response_model=CallDetailOut)
async def get_call(call_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(
        select(Call)
        .where(Call.id == call_id)
        .options(
            selectinload(Call.operator),
            selectinload(Call.scenario),
            selectinload(Call.transcriptions),
            selectinload(Call.analysis_results),
            selectinload(Call.tags).selectinload(CallTag.tag),
            selectinload(Call.notes).selectinload(SupervisorNote.user),
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    audio_url = f"/api/v1/calls/{call.id}/audio" if call.audio_path else None

    notes = [
        NoteOut(id=n.id, text=n.text, user_name=n.user.full_name, created_at=n.created_at) for n in call.notes
    ]
    latest_trans = sorted(call.transcriptions, key=lambda t: t.id, reverse=True)[:1]
    duration = call.duration
    if duration is None and latest_trans:
        duration = duration_seconds_from_utterances(latest_trans[0].utterances)
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
        transcriptions=latest_trans,
        analysis_results=call.analysis_results,
        notes=notes,
    )


@router.get("/{call_id}/audio")
async def stream_call_audio(
    call_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call or not call.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    data = storage_service.download_bytes(call.audio_path)
    return Response(
        content=data,
        media_type=storage_service.media_type_for_key(call.audio_path),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/{call_id}/reanalyze", response_model=MessageOut)
async def reanalyze(
    call_id: int,
    scenario_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from worker.task_lock import is_locked
    from worker.tasks.pipeline import reanalyze_call

    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    # Busy is decided by the worker lock, not by call.status: a status left over
    # from a crashed worker must not block retries forever.
    if is_locked("analyze", call_id) or is_locked("transcribe", call_id):
        raise HTTPException(status_code=409, detail="Звонок уже обрабатывается")
    call.status = "analyzing"
    call.error_message = None
    await db.commit()
    reanalyze_call.delay(call_id, scenario_id)
    return MessageOut(message="Reanalysis queued")


@router.post("/{call_id}/retranscribe", response_model=MessageOut)
async def retranscribe(call_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    from worker.task_lock import is_locked
    from worker.tasks.pipeline import retranscribe_call

    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if not call.audio_path:
        raise HTTPException(status_code=400, detail="Call has no audio file")
    if is_locked("analyze", call_id) or is_locked("transcribe", call_id):
        raise HTTPException(status_code=409, detail="Звонок уже обрабатывается — дождитесь завершения")
    call.status = "transcribing"
    call.error_message = None
    await db.commit()
    retranscribe_call.delay(call_id)
    return MessageOut(message="Retranscription queued")


@router.patch("/{call_id}/tags", response_model=MessageOut)
async def update_tags(
    call_id: int,
    body: CallTagsUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    await db.execute(CallTag.__table__.delete().where(CallTag.call_id == call_id))
    if body.tag_ids:
        existing = await db.execute(select(Tag.id).where(Tag.id.in_(body.tag_ids)))
        valid_ids = {row[0] for row in existing.all()}
        unknown = set(body.tag_ids) - valid_ids
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown tag ids: {sorted(unknown)}")
        for tag_id in body.tag_ids:
            db.add(CallTag(call_id=call_id, tag_id=tag_id))
    await db.commit()
    return MessageOut(message="Tags updated")


@router.post("/{call_id}/notes", response_model=NoteOut)
async def add_note(
    call_id: int,
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Call).where(Call.id == call_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Call not found")
    note = SupervisorNote(call_id=call_id, user_id=user.id, text=body.text)
    db.add(note)
    await db.flush()
    await db.commit()
    return NoteOut(id=note.id, text=note.text, user_name=user.full_name, created_at=note.created_at)
