from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Tag
from app.schemas.common import Paginated
from app.schemas.tags import TagOut


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


class TagService:
    async def list_tags(
        self, db: AsyncSession, *, q: str | None, page: int, page_size: int
    ) -> Paginated[TagOut]:
        stmt = select(Tag).order_by(Tag.name.asc())
        count_stmt = select(func.count()).select_from(Tag)
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(Tag.name.ilike(pattern))
            count_stmt = count_stmt.where(Tag.name.ilike(pattern))
        total = await db.scalar(count_stmt) or 0
        result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        items = [TagOut.model_validate(t) for t in result.scalars().all()]
        return Paginated(items=items, total=total, page=page, page_size=page_size)

    async def create(self, db: AsyncSession, name: str) -> TagOut:
        name = _normalize_name(name)
        if not name:
            raise AppError.invalid("Название тега не может быть пустым")
        existing = await db.execute(select(Tag).where(func.lower(Tag.name) == name.lower()))
        tag = existing.scalar_one_or_none()
        if tag:
            return TagOut.model_validate(tag)
        tag = Tag(name=name)
        db.add(tag)
        await db.flush()
        await db.refresh(tag)
        return TagOut.model_validate(tag)


tag_service = TagService()
