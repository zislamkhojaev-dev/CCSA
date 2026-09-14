import asyncio
import json

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.deps import get_admin_user, get_current_user
from app.database import get_db
from app.models import User
from app.schemas.common import MessageOut, Paginated
from app.schemas.research import (
    ResearchCreateIn,
    ResearchDetailOut,
    ResearchFilterOptionsOut,
    ResearchListItem,
    ResearchPreviewIn,
    ResearchPreviewOut,
)
from app.services.feature_flags import require_feature
from app.services.idempotency import begin_idempotency, idempotency_key_header, store_idempotency
from app.services.redis_events import subscribe_research_events
from app.services.research_service import research_service

router = APIRouter()


@router.get("", response_model=Paginated[ResearchListItem])
async def list_research(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await require_feature(db, "research")
    return await research_service.list_studies(db, page=page, page_size=page_size)


@router.get("/filter-options", response_model=ResearchFilterOptionsOut)
async def research_filter_options(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await require_feature(db, "research")
    return await research_service.filter_options(db)


@router.post("/preview", response_model=ResearchPreviewOut)
async def preview_research(
    body: ResearchPreviewIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await require_feature(db, "research")
    return await research_service.preview(db, body.filters)


@router.post("", response_model=ResearchDetailOut, status_code=status.HTTP_201_CREATED)
async def create_research(
    body: ResearchCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    idem_key: str | None = Depends(idempotency_key_header),
):
    await require_feature(db, "research")
    replay = await begin_idempotency(
        db, user_id=user.id, key=idem_key, method="POST", path="/research", body=body.model_dump()
    )
    if replay.replay:
        return ResearchDetailOut(**replay.payload)
    out = await research_service.create(db, user, body)
    if idem_key:
        await store_idempotency(
            db,
            user_id=user.id,
            key=idem_key,
            method="POST",
            path="/research",
            body=body.model_dump(),
            status_code=201,
            payload=out.model_dump(mode="json"),
        )
    return out


@router.get("/{study_id}", response_model=ResearchDetailOut)
async def get_research(
    study_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_feature(db, "research")
    return await research_service.detail(db, study_id, user)


@router.get("/{study_id}/export")
async def export_research(
    study_id: int,
    format: str = Query("md", pattern="^(md|json)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_feature(db, "research")
    kind, payload, filename = await research_service.export(db, study_id, user, format)
    if kind == "json":
        return JSONResponse(
            content=payload,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return Response(
        content="\ufeff" + payload,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{study_id}/events")
async def research_events(
    study_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await require_feature(db, "research")
    await research_service.get(db, study_id, user)

    async def generator():
        pubsub = subscribe_research_events(study_id)
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


@router.delete("/{study_id}", response_model=MessageOut)
async def delete_research(
    study_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_admin_user),
):
    await require_feature(db, "research")
    await research_service.delete(db, study_id, user)
    return MessageOut(message="Deleted")
