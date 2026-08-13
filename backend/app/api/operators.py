import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import AnalysisResult, Call, Operator, User
from app.schemas.common import Paginated
from app.schemas.operators import OperatorOut, OperatorSyncOut
from app.services.operator_sync import (
    OPERATOR_LOOKBACK_DAYS,
    extract_operators,
    operator_lookback_start,
)
from app.services.settings_store import get_setting
from app.services.webitel import WebitelClient

logger = logging.getLogger(__name__)

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
    op_ids = [op.id for op in ops]
    calls_by_op: dict[int, int] = {}
    avg_by_op: dict[int, float] = {}
    if op_ids:
        count_rows = await db.execute(
            select(Call.operator_id, func.count())
            .where(Call.operator_id.in_(op_ids))
            .group_by(Call.operator_id)
        )
        calls_by_op = {op_id: int(cnt) for op_id, cnt in count_rows.all() if op_id is not None}
        avg_rows = await db.execute(
            select(Call.operator_id, func.avg(AnalysisResult.total_score))
            .join(AnalysisResult, AnalysisResult.call_id == Call.id)
            .where(Call.operator_id.in_(op_ids))
            .group_by(Call.operator_id)
        )
        avg_by_op = {
            op_id: float(avg) for op_id, avg in avg_rows.all() if op_id is not None and avg is not None
        }
    items = [
        OperatorOut(
            id=op.id,
            webitel_id=op.webitel_id,
            full_name=op.full_name,
            team_name=op.team_name,
            is_active=op.is_active,
            calls_count=calls_by_op.get(op.id, 0),
            avg_score=round(avg_by_op[op.id], 1) if op.id in avg_by_op else None,
        )
        for op in ops
    ]
    return Paginated(items=items, total=total, page=page, page_size=page_size)


@router.post("/sync", response_model=OperatorSyncOut)
async def sync_operators(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Import operators from recent Webitel call history.

    Runs inline rather than as a background task so the UI can report how many
    operators were actually added instead of just "queued".
    """
    api_url = await get_setting(db, "webitel_api_url")
    if not api_url:
        raise HTTPException(
            status_code=400,
            detail="Webitel не настроен — укажите URL в «Настройки → Коннекторы»",
        )
    token = await get_setting(db, "webitel_access_token")

    try:
        items = await WebitelClient(api_url, token).fetch_call_history(
            created_from=operator_lookback_start()
        )
    except Exception as e:
        logger.warning("Operator sync failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Webitel недоступен: {e}") from e

    pairs = extract_operators(items)
    created = 0
    for webitel_id, full_name in pairs:
        exists = await db.scalar(select(Operator.id).where(Operator.webitel_id == webitel_id))
        if exists:
            continue
        db.add(Operator(webitel_id=webitel_id, full_name=full_name, is_active=True))
        created += 1
    await db.commit()

    if created:
        message = f"Добавлено операторов: {created} (найдено в Webitel: {len(pairs)})"
    elif pairs:
        message = f"Новых операторов нет — все {len(pairs)} уже в списке"
    else:
        message = (
            f"В истории Webitel за последние {OPERATOR_LOOKBACK_DAYS} дней операторы не найдены"
        )

    return OperatorSyncOut(
        message=message, created=created, found=len(pairs), calls_scanned=len(items)
    )
