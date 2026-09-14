from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.common import Paginated
from app.schemas.tags import TagCreate, TagOut
from app.services.tag_service import tag_service

router = APIRouter()


@router.get("", response_model=Paginated[TagOut])
async def list_tags(
    q: str | None = Query(None, description="Поиск по названию"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await tag_service.list_tags(db, q=q, page=page, page_size=page_size)


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await tag_service.create(db, body.name)
