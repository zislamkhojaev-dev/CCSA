import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode, USER_ERROR_WEBITEL
from app.core.logging import log_error
from app.models import AnalysisResult, Call, Operator
from app.ports import WebitelPort
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


class OperatorService:
    def __init__(self, webitel_factory=None) -> None:
        self._webitel_factory = webitel_factory or (lambda url, token: WebitelClient(url, token))

    async def list_operators(
        self, db: AsyncSession, *, page: int, page_size: int
    ) -> Paginated[OperatorOut]:
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
                op_id: float(avg)
                for op_id, avg in avg_rows.all()
                if op_id is not None and avg is not None
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

    async def sync_operators(self, db: AsyncSession, webitel: WebitelPort | None = None) -> OperatorSyncOut:
        api_url = await get_setting(db, "webitel_api_url")
        if not api_url:
            raise AppError.invalid("Webitel не настроен — укажите URL в «Настройки → Коннекторы»")
        token = await get_setting(db, "webitel_access_token")
        client = webitel or self._webitel_factory(api_url, token)
        try:
            items = await client.fetch_call_history(created_from=operator_lookback_start())
        except AppError:
            raise
        except Exception as e:
            log_error(logger, "Operator sync failed", method="sync_operators", exc=e)
            raise AppError(ErrorCode.EXT_WEBITEL_UNAVAILABLE, USER_ERROR_WEBITEL, 502) from e

        pairs = extract_operators(items)
        created = 0
        for webitel_id, full_name in pairs:
            exists = await db.scalar(select(Operator.id).where(Operator.webitel_id == webitel_id))
            if exists:
                continue
            db.add(Operator(webitel_id=webitel_id, full_name=full_name, is_active=True))
            created += 1
        await db.flush()

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


operator_service = OperatorService()
