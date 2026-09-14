import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import AnalysisResult, Call
from app.schemas.dashboard import (
    DashboardLayoutOut,
    DashboardWidgetConfig,
    DashboardSummary,
    ScoreBucket,
)
from app.services.dashboard_metrics import AVAILABLE_METRICS
from app.services.quality_settings import load_quality_config
from app.services.settings_store import get_setting, set_setting

DEFAULT_WIDGETS = [
    DashboardWidgetConfig(
        id="w1", type="count", title="Всего звонков", metric="calls_total", width=1, height=1
    ),
    DashboardWidgetConfig(
        id="w2", type="count", title="Проанализировано", metric="calls_analyzed", width=1, height=1
    ),
    DashboardWidgetConfig(
        id="w3", type="kpi", title="Средний балл", metric="score_avg", width=1, height=1
    ),
    DashboardWidgetConfig(
        id="w4", type="count", title="Нарушения", metric="violations_count", width=1, height=1
    ),
    DashboardWidgetConfig(
        id="w5", type="count", title="Звонков сегодня", metric="calls_today", width=1, height=1
    ),
    DashboardWidgetConfig(
        id="w6",
        type="chart",
        title="Распределение оценок",
        metric="score_distribution",
        width=4,
        height=2,
    ),
]


def _layout_key(user_id: int) -> str:
    return f"dashboard_layout_user_{user_id}"


class DashboardService:
    async def load_user_widgets(self, db: AsyncSession, user_id: int) -> list[DashboardWidgetConfig]:
        raw = await get_setting(db, _layout_key(user_id), "")
        if not raw:
            return DEFAULT_WIDGETS
        try:
            data = json.loads(raw)
            return [DashboardWidgetConfig(**w) for w in data.get("widgets", [])]
        except (json.JSONDecodeError, TypeError, ValueError):
            return DEFAULT_WIDGETS

    async def summary(self, db: AsyncSession) -> DashboardSummary:
        quality = await load_quality_config(db)
        good = quality.threshold_good
        mid = quality.threshold_mid
        total = await db.scalar(select(func.count()).select_from(Call)) or 0
        analyzed = await db.scalar(
            select(func.count()).select_from(Call).where(Call.status == "analyzed")
        ) or 0
        avg = await db.scalar(select(func.avg(AnalysisResult.total_score)).select_from(AnalysisResult))
        violations = await db.scalar(
            select(func.count()).select_from(AnalysisResult).where(AnalysisResult.is_violation.is_(True))
        ) or 0

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        calls_today = await db.scalar(
            select(func.count()).select_from(Call).where(Call.created_at >= today_start)
        ) or 0

        green = await db.scalar(
            select(func.count()).select_from(AnalysisResult).where(AnalysisResult.total_score >= good)
        ) or 0
        yellow = await db.scalar(
            select(func.count())
            .select_from(AnalysisResult)
            .where(AnalysisResult.total_score >= mid, AnalysisResult.total_score < good)
        ) or 0
        red = await db.scalar(
            select(func.count()).select_from(AnalysisResult).where(AnalysisResult.total_score < mid)
        ) or 0

        return DashboardSummary(
            total_calls=total,
            analyzed_calls=analyzed,
            avg_score=round(float(avg), 1) if avg else None,
            violations_count=violations,
            calls_today=calls_today,
            score_distribution=[
                ScoreBucket(label=f">{good}%", count=green),
                ScoreBucket(label=f"{mid}-{good}%", count=yellow),
                ScoreBucket(label=f"<{mid}%", count=red),
            ],
            top_violations=[],
        )

    async def save_layout(
        self, db: AsyncSession, user_id: int, widgets: list[DashboardWidgetConfig]
    ) -> DashboardLayoutOut:
        for w in widgets:
            if w.metric not in AVAILABLE_METRICS:
                raise AppError.invalid(f"Unknown metric: {w.metric}")
        payload = json.dumps({"widgets": [w.model_dump() for w in widgets]})
        await set_setting(db, _layout_key(user_id), payload)
        return DashboardLayoutOut(widgets=widgets)


dashboard_service = DashboardService()
