from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Tag, User
from app.schemas.tags import TagCreate, TagOut

router = APIRouter()


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


@router.get("", response_model=list[TagOut])
async def list_tags(
    q: str | None = Query(None, description="Поиск по названию"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Tag).order_by(Tag.name.asc()).limit(limit)
    if q and q.strip():
        stmt = stmt.where(Tag.name.ilike(f"%{q.strip()}%"))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    name = _normalize_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Название тега не может быть пустым")

    existing = await db.execute(select(Tag).where(func.lower(Tag.name) == name.lower()))
    tag = existing.scalar_one_or_none()
    if tag:
        return tag

    tag = Tag(name=name)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag
