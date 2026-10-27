import asyncio
import json

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.common import MessageOut
from app.schemas.playground import PlaygroundJobCreate, PlaygroundJobOut
from app.services.audio_stream import stream_audio
from app.services.feature_flags import require_feature
from app.services.idempotency import begin_idempotency, idempotency_key_header, store_idempotency
from app.services.playground_service import playground_service
from app.services.uploads import read_bounded_uploads
from app.services.redis_events import subscribe_playground_events

router = APIRouter()


@router.post("/jobs", response_model=PlaygroundJobOut)
async def create_job(
    body: PlaygroundJobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    idem_key: str | None = Depends(idempotency_key_header),
):
    await require_feature(db, "playground")
    replay = await begin_idempotency(
        db, user_id=user.id, key=idem_key, method="POST", path="/playground/jobs", body=body.model_dump()
    )
    if replay.replay:
        return PlaygroundJobOut(**replay.payload)
    out = await playground_service.create_job(db, user, body)
    if idem_key:
        await store_idempotency(
            db,
            user_id=user.id,
            key=idem_key,
            method="POST",
            path="/playground/jobs",
            body=body.model_dump(),
            status_code=200,
            payload=out.model_dump(mode="json"),
        )
    return out


@router.post("/jobs/{job_id}/upload")
async def upload_files(
    job_id: int,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_feature(db, "playground")
    payloads = await read_bounded_uploads(files)
    count = await playground_service.upload_files(db, job_id, user, payloads)
    return {"message": f"Uploaded {count} file(s)", "queued": count}


@router.post("/jobs/{job_id}/run", response_model=MessageOut)
async def run_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_feature(db, "playground")
    n = await playground_service.run_job(db, job_id, user)
    return MessageOut(message=f"Запущен анализ {n} файл(ов)")


@router.get("/jobs/{job_id}", response_model=PlaygroundJobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await require_feature(db, "playground")
    return await playground_service.get_job(db, job_id, user)


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await require_feature(db, "playground")
    await playground_service.assert_job_owner(db, job_id, user)

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
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_feature(db, "playground")
    path = await playground_service.audio_path(db, file_id, user)
    return stream_audio(request, path)


@router.post("/files/{file_id}/promote-to-calls", response_model=MessageOut)
async def promote_to_calls(
    file_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await require_feature(db, "playground")
    call_id = await playground_service.promote_file(db, file_id, user)
    return MessageOut(message=f"Promoted to call #{call_id}")


@router.post("/jobs/{job_id}/promote-to-calls", response_model=MessageOut)
async def promote_job_to_calls(
    job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await require_feature(db, "playground")
    call_ids = await playground_service.promote_job(db, job_id, user)
    return MessageOut(message=f"Сохранено в общую базу: {len(call_ids)} звонок(ов)")
