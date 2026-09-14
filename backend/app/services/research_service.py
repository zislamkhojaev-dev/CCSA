from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models import Operator, ResearchStudy, Tag, User
from app.schemas.common import Paginated
from app.schemas.research import (
    ResearchCreateIn,
    ResearchDetailOut,
    ResearchFilterOptionsOut,
    ResearchListItem,
    ResearchPreviewOut,
)
from app.schemas.tags import TagOut
from app.services.research_export import (
    build_research_json_export,
    build_research_markdown_export,
    research_export_filename,
)
from app.services.research_query import build_research_calls_query, build_research_count_query
from app.services.research_utils import filters_to_json, filters_to_query_kwargs, research_max_calls
from app.services.task_dispatch import task_dispatcher


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


class ResearchService:
    async def list_studies(
        self, db: AsyncSession, *, page: int, page_size: int
    ) -> Paginated[ResearchListItem]:
        total = await db.scalar(select(func.count()).select_from(ResearchStudy)) or 0
        result = await db.execute(
            select(ResearchStudy)
            .options(selectinload(ResearchStudy.user))
            .order_by(ResearchStudy.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return Paginated(
            items=[_list_item(s) for s in result.scalars().all()],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def filter_options(self, db: AsyncSession) -> ResearchFilterOptionsOut:
        cap = get_settings().filter_options_limit
        queue_rows = await db.execute(
            select(Operator.team_name)
            .where(Operator.team_name.isnot(None), Operator.team_name != "")
            .distinct()
            .order_by(Operator.team_name)
            .limit(cap)
        )
        tag_rows = await db.execute(select(Tag).order_by(Tag.name).limit(cap))
        return ResearchFilterOptionsOut(
            queues=[r[0] for r in queue_rows.all() if r[0]],
            tags=[TagOut.model_validate(t) for t in tag_rows.scalars().all()],
        )

    async def preview(self, db: AsyncSession, filters) -> ResearchPreviewOut:
        kw = filters_to_query_kwargs(filters)
        count = await db.scalar(build_research_count_query(**kw)) or 0
        return ResearchPreviewOut(count=count, max_calls=research_max_calls())

    async def create(self, db: AsyncSession, user: User, body: ResearchCreateIn) -> ResearchDetailOut:
        kw = filters_to_query_kwargs(body.filters)
        max_calls = research_max_calls()
        count = await db.scalar(build_research_count_query(**kw)) or 0
        if count == 0:
            raise AppError.invalid("По выбранным фильтрам нет звонков с транскриптом")
        if count > max_calls:
            raise AppError.invalid(f"Слишком много звонков ({count}). Максимум: {max_calls}. Сузьте фильтры.")
        result = await db.execute(build_research_calls_query(**kw).limit(max_calls))
        call_ids = [row[0] for row in result.all()]
        if not call_ids:
            raise AppError.invalid("По выбранным фильтрам нет звонков с транскриптом")
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
        loaded = await db.execute(
            select(ResearchStudy).where(ResearchStudy.id == study.id).options(selectinload(ResearchStudy.user))
        )
        study = loaded.scalar_one()
        await db.commit()
        task_dispatcher.run_research_study(study.id)
        return _detail_out(study)

    async def get(self, db: AsyncSession, study_id: int, user: User) -> ResearchStudy:
        study = await db.get(ResearchStudy, study_id, options=[selectinload(ResearchStudy.user)])
        if not study:
            raise AppError.not_found("Research study not found")
        if study.user_id != user.id and user.role != "admin":
            raise AppError.not_found("Research study not found")
        return study

    async def detail(self, db: AsyncSession, study_id: int, user: User) -> ResearchDetailOut:
        return _detail_out(await self.get(db, study_id, user))

    async def export(self, db: AsyncSession, study_id: int, user: User, fmt: str):
        study = await self.get(db, study_id, user)
        if study.status != "completed" or not study.report_markdown:
            raise AppError(ErrorCode.JOB_NOT_READY, "Отчёт ещё не готов для экспорта", 400)
        if fmt == "json":
            return (
                "json",
                build_research_json_export(study),
                research_export_filename(study.id, study.title, ext="json"),
            )
        return (
            "md",
            build_research_markdown_export(study),
            research_export_filename(study.id, study.title, ext="md"),
        )

    async def delete(self, db: AsyncSession, study_id: int, user: User) -> None:
        study = await self.get(db, study_id, user)
        await db.delete(study)


research_service = ResearchService()
