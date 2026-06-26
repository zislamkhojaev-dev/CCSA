import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Operator, ResearchStudy, Tag, User
from app.schemas.common import MessageOut, Paginated
from app.schemas.research import (
    ResearchCreateIn,
    ResearchDetailOut,
    ResearchFilterOptionsOut,
    ResearchListItem,
    ResearchPreviewIn,
    ResearchPreviewOut,
)
from app.schemas.tags import TagOut
from app.services.redis_events import subscribe_research_events
from app.services.research_export import (
    build_research_json_export,
    build_research_markdown_export,
    research_export_filename,
)
from app.services.research_query import build_research_calls_query, build_research_count_query
from app.services.research_utils import filters_to_json, filters_to_query_kwargs, research_max_calls

router = APIRouter()


def _list_item(study: ResearchStudy) -> ResearchListItem:
    return ResearchListItem(
        id=study.id,
        title=study.title,
        status=study.status,
        call_count=study.call_count,
        filters_json=study.filters_json or {},
        user_name=study.user.full_name if study.user else None,
        created_at=study.created_at,
        finished_at=study.finished_at,
    )


def _detail_out(study: ResearchStudy) -> ResearchDetailOut:
    call_ids = study.call_ids
    if call_ids is not None and not isinstance(call_ids, list):
        call_ids = None
    return ResearchDetailOut(
        id=study.id,
        title=study.title,
        prompt=study.prompt,
        filters_json=study.filters_json or {},
        status=study.status,
        call_count=study.call_count,
        call_ids=call_ids,
        llm_model=study.llm_model,
        report_markdown=study.report_markdown,
        error_message=study.error_message,
        user_name=study.user.full_name if study.user else None,
        created_at=study.created_at,
        finished_at=study.finished_at,
    )


@router.get("", response_model=Paginated[ResearchListItem])
async def list_research(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    total = await db.scalar(select(func.count()).select_from(ResearchStudy)) or 0
    result = await db.execute(
        select(ResearchStudy)
        .options(selectinload(ResearchStudy.user))
        .order_by(ResearchStudy.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_list_item(s) for s in result.scalars().all()]
    return Paginated(items=items, total=total, page=page, page_size=page_size)


@router.get("/filter-options", response_model=ResearchFilterOptionsOut)
async def research_filter_options(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    queue_rows = await db.execute(
        select(Operator.team_name)
        .where(Operator.team_name.isnot(None), Operator.team_name != "")
        .distinct()
        .order_by(Operator.team_name)
    )
    tag_rows = await db.execute(select(Tag).order_by(Tag.name))
    return ResearchFilterOptionsOut(
        queues=[r[0] for r in queue_rows.all() if r[0]],
        tags=[TagOut.model_validate(t) for t in tag_rows.scalars().all()],
    )


@router.post("/preview", response_model=ResearchPreviewOut)
async def preview_research(
    body: ResearchPreviewIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    kw = filters_to_query_kwargs(body.filters)
    count = await db.scalar(build_research_count_query(**kw)) or 0
    return ResearchPreviewOut(count=count, max_calls=research_max_calls())


@router.post("", response_model=ResearchDetailOut, status_code=status.HTTP_201_CREATED)
async def create_research(
    body: ResearchCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kw = filters_to_query_kwargs(body.filters)
    max_calls = research_max_calls()
    count = await db.scalar(build_research_count_query(**kw)) or 0
    if count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="По выбранным фильтрам нет звонков с транскриптом",
        )
    if count > max_calls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Слишком много звонков ({count}). Максимум: {max_calls}. Сузьте фильтры.",
        )

    result = await db.execute(build_research_calls_query(**kw).limit(max_calls))
    call_ids = [row[0] for row in result.all()]
    if not call_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="По выбранным фильтрам нет звонков с транскриптом",
        )

    study = ResearchStudy(
        title=body.title.strip(),
        prompt=body.prompt.strip(),
        filters_json=filters_to_json(body.filters),
        status="pending",
        user_id=user.id,
        call_count=0,
        call_ids=call_ids,
    )
    db.add(study)
    await db.flush()
    result = await db.execute(
        select(ResearchStudy)
        .where(ResearchStudy.id == study.id)
        .options(selectinload(ResearchStudy.user))
    )
    study = result.scalar_one()

    await db.commit()

    from worker.tasks.research import run_research_study

    run_research_study.delay(study.id)

    return _detail_out(study)


@router.get("/{study_id}", response_model=ResearchDetailOut)
async def get_research(
    study_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    study = await db.get(
        ResearchStudy,
        study_id,
        options=[selectinload(ResearchStudy.user)],
    )
    if not study:
        raise HTTPException(status_code=404, detail="Research study not found")
    return _detail_out(study)


@router.get("/{study_id}/export")
async def export_research(
    study_id: int,
    format: str = Query("md", pattern="^(md|json)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    study = await db.get(
        ResearchStudy,
        study_id,
        options=[selectinload(ResearchStudy.user)],
    )
    if not study:
        raise HTTPException(status_code=404, detail="Research study not found")
    if study.status != "completed" or not study.report_markdown:
        raise HTTPException(status_code=400, detail="Отчёт ещё не готов для экспорта")

    if format == "json":
        payload = build_research_json_export(study)
        filename = research_export_filename(study.id, study.title, ext="json")
        return JSONResponse(
            content=payload,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    markdown = build_research_markdown_export(study)
    filename = research_export_filename(study.id, study.title, ext="md")
    return Response(
        content="\ufeff" + markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{study_id}/events")
async def research_events(study_id: int, _: User = Depends(get_current_user)):
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
    _: User = Depends(get_current_user),
):
    study = await db.get(ResearchStudy, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Research study not found")
    await db.delete(study)
    return MessageOut(message="Deleted")
