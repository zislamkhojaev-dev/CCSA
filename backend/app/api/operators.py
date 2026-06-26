from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import AnalysisResult, Call, Operator, User
from app.schemas.common import Paginated
from app.schemas.operators import OperatorOut

router = APIRouter()


@router.get("", response_model=Paginated[OperatorOut])
async def list_operators(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    total = await db.scalar(select(func.count()).select_from(Operator)) or 0
    result = await db.execute(
        select(Operator).order_by(Operator.full_name).offset((page - 1) * page_size).limit(page_size)
    )
    ops = result.scalars().all()
    items = []
    for op in ops:
        calls_count = await db.scalar(select(func.count()).select_from(Call).where(Call.operator_id == op.id)) or 0
        avg = await db.scalar(
            select(func.avg(AnalysisResult.total_score))
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(Call.operator_id == op.id)
        )
        items.append(
            OperatorOut(
                id=op.id,
                webitel_id=op.webitel_id,
                full_name=op.full_name,
                team_name=op.team_name,
                is_active=op.is_active,
                calls_count=calls_count,
                avg_score=round(float(avg), 1) if avg else None,
            )
        )
    return Paginated(items=items, total=total, page=page, page_size=page_size)


@router.post("/sync", response_model=dict)
async def sync_operators(_: User = Depends(get_current_user)):
    from worker.tasks.webitel import sync_operators_from_webitel

    sync_operators_from_webitel.delay()
    return {"message": "Operator sync queued"}
