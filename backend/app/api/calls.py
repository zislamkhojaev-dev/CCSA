import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.deps import get_admin_user, get_current_user
from app.database import get_db
from app.models import User
from app.schemas.calls import (
    CallBulkDelete,
    CallDetailOut,
    CallExportJobCreate,
    CallExportJobOut,
    CallExportSyncBody,
    CallListItem,
    CallStatusOut,
    CallTagsUpdate,
    NoteCreate,
    NoteOut,
)
from app.schemas.common import MessageOut, Paginated
from app.services.audio_stream import stream_audio
from app.services.call_service import call_service, parse_date
from app.services.calls_export import encode_export_file
from app.services.idempotency import begin_idempotency, idempotency_key_header, store_idempotency
from app.services.redis_events import subscribe_call_export_events

router = APIRouter()


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
    return await call_service.list_calls(
        db,
        page=page,
        page_size=page_size,
        status_filter=status_filter or None,
        operator_match=operator_match,
        operator_value=operator_value,
        client_match=client_match,
        client_value=client_value,
        date_from=parse_date(date_from),
        date_to=parse_date(date_to, end_of_day=True),
        duration_op=duration_op,
        duration_value=duration_value,
        score_op=score_op,
        score_value=score_value,
        tag_id=tag_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post("/bulk-delete", response_model=MessageOut)
async def bulk_delete_calls(
    body: CallBulkDelete,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_admin_user),
    idem_key: str | None = Depends(idempotency_key_header),
):
    replay = await begin_idempotency(
        db, user_id=user.id, key=idem_key, method="POST", path="/calls/bulk-delete", body=body.model_dump()
    )
    if replay.replay:
        return MessageOut(**replay.payload)
    deleted = await call_service.bulk_delete(db, body.ids)
    payload = MessageOut(message=f"Deleted {deleted} call(s)")
    if idem_key:
        await store_idempotency(
            db,
            user_id=user.id,
            key=idem_key,
            method="POST",
            path="/calls/bulk-delete",
            body=body.model_dump(),
            status_code=200,
            payload=payload.model_dump(),
        )
    return payload


@router.post("/export")
async def export_calls_sync(
    body: CallExportSyncBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = await call_service.export_sync_rows(db, body.ids)
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
    idem_key: str | None = Depends(idempotency_key_header),
):
    replay = await begin_idempotency(
        db, user_id=user.id, key=idem_key, method="POST", path="/calls/export/jobs", body=body.model_dump()
    )
    if replay.replay:
        return CallExportJobOut(**replay.payload)
    out = await call_service.create_export_job(db, user, body)
    if idem_key:
        await store_idempotency(
            db,
            user_id=user.id,
            key=idem_key,
            method="POST",
            path="/calls/export/jobs",
            body=body.model_dump(),
            status_code=200,
            payload=out.model_dump(mode="json"),
        )
    return out


@router.get("/export/jobs/{job_id}", response_model=CallExportJobOut)
async def get_call_export_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await call_service.get_owned_export_job(db, job_id, user)
    return call_service.export_job_out(job)


@router.get("/export/jobs/{job_id}/events")
async def call_export_job_events(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await call_service.get_owned_export_job(db, job_id, user)

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
    job = await call_service.get_owned_export_job(db, job_id, user)
    content = call_service.download_export_bytes(job)
    ext = "csv" if job.format == "csv" else "json"
    media = "text/csv; charset=utf-8" if ext == "csv" else "application/json; charset=utf-8"
    filename = f"calls-export-{job.id}.{ext}"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{call_id}/status", response_model=CallStatusOut)
async def get_call_status(
    call_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    return await call_service.get_status(db, call_id)


@router.get("/{call_id}", response_model=CallDetailOut)
async def get_call(call_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await call_service.get_detail(db, call_id)


@router.get("/{call_id}/audio")
async def stream_call_audio(
    call_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    path = await call_service.get_audio_path(db, call_id)
    return stream_audio(request, path)


@router.post("/{call_id}/reanalyze", response_model=MessageOut)
async def reanalyze(
    call_id: int,
    scenario_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    await call_service.reanalyze(db, call_id, scenario_id)
    return MessageOut(message="Reanalysis queued")


@router.post("/{call_id}/retranscribe", response_model=MessageOut)
async def retranscribe(call_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)):
    await call_service.retranscribe(db, call_id)
    return MessageOut(message="Retranscription queued")


@router.patch("/{call_id}/tags", response_model=MessageOut)
async def update_tags(
    call_id: int,
    body: CallTagsUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await call_service.update_tags(db, call_id, body.tag_ids)
    return MessageOut(message="Tags updated")


@router.post("/{call_id}/notes", response_model=NoteOut)
async def add_note(
    call_id: int,
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    idem_key: str | None = Depends(idempotency_key_header),
):
    replay = await begin_idempotency(
        db,
        user_id=user.id,
        key=idem_key,
        method="POST",
        path=f"/calls/{call_id}/notes",
        body=body.model_dump(),
    )
    if replay.replay:
        return NoteOut(**replay.payload)
    note = await call_service.add_note(db, call_id, user, body.text)
    if idem_key:
        await store_idempotency(
            db,
            user_id=user.id,
            key=idem_key,
            method="POST",
            path=f"/calls/{call_id}/notes",
            body=body.model_dump(),
            status_code=200,
            payload=note.model_dump(mode="json"),
        )
    return note
