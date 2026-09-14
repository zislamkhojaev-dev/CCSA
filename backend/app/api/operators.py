from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_admin_user, get_current_user
from app.database import get_db
from app.models import User
from app.schemas.common import Paginated
from app.schemas.operators import OperatorOut, OperatorSyncOut
from app.services.feature_flags import require_feature
from app.services.operator_service import operator_service

router = APIRouter()


@router.get("", response_model=Paginated[OperatorOut])
async def list_operators(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await operator_service.list_operators(db, page=page, page_size=page_size)


@router.post("/sync", response_model=OperatorSyncOut)
async def sync_operators(db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)):
    await require_feature(db, "webitel_sync")
    return await operator_service.sync_operators(db)
