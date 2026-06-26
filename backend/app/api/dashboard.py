import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import AnalysisResult, Call, User
from app.schemas.dashboard import (
    DashboardLayoutOut,
    DashboardLayoutUpdate,
    DashboardSummary,
    DashboardWidgetConfig,
    ScoreBucket,
    WidgetMetricResponse,
)
from app.services.dashboard_metrics import AVAILABLE_METRICS, fetch_widget_metric
from app.services.settings_store import get_setting, set_setting

router = APIRouter()

DEFAULT_WIDGETS = [
    DashboardWidgetConfig(
        id="w1", type="count", title="Всего звонков", metric="calls_total", size="small"
    ),
    DashboardWidgetConfig(
        id="w2", type="count", title="Проанализировано", metric="calls_analyzed", size="small"
    ),
    DashboardWidgetConfig(
        id="w3", type="kpi", title="Средний балл", metric="score_avg", size="small"
    ),
    DashboardWidgetConfig(
        id="w4", type="count", title="Нарушения", metric="violations_count", size="small"
    ),
    DashboardWidgetConfig(
        id="w5", type="count", title="Звонков сегодня", metric="calls_today", size="small"
    ),
    DashboardWidgetConfig(
        id="w6",
        type="chart",
        title="Распределение оценок",
        metric="score_distribution",
        size="large",
    ),
]


def _layout_key(user_id: int) -> str:
    return f"dashboard_layout_user_{user_id}"


@router.get("/summary", response_model=DashboardSummary)
async def summary(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
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
        select(func.count()).select_from(AnalysisResult).where(AnalysisResult.total_score >= 80)
    ) or 0
    yellow = await db.scalar(
        select(func.count())
        .select_from(AnalysisResult)
        .where(AnalysisResult.total_score >= 50, AnalysisResult.total_score < 80)
    ) or 0
    red = await db.scalar(
        select(func.count()).select_from(AnalysisResult).where(AnalysisResult.total_score < 50)
    ) or 0

    return DashboardSummary(
        total_calls=total,
        analyzed_calls=analyzed,
        avg_score=round(float(avg), 1) if avg else None,
        violations_count=violations,
        calls_today=calls_today,
        score_distribution=[
            ScoreBucket(label=">80%", count=green),
            ScoreBucket(label="50-80%", count=yellow),
            ScoreBucket(label="<50%", count=red),
        ],
        top_violations=[],
    )


@router.get("/metrics/available", response_model=list[str])
async def list_metrics(_: User = Depends(get_current_user)):
    return AVAILABLE_METRICS


@router.get("/metrics", response_model=WidgetMetricResponse)
async def widget_metric(
    metric: str = Query(..., description="Metric key"),
    period_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if metric not in AVAILABLE_METRICS:
        raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")
    return await fetch_widget_metric(db, metric, period_days)


@router.get("/layout", response_model=DashboardLayoutOut)
async def get_layout(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = await get_setting(db, _layout_key(user.id), "")
    if not raw:
        return DashboardLayoutOut(widgets=DEFAULT_WIDGETS)
    try:
        data = json.loads(raw)
        return DashboardLayoutOut(widgets=[DashboardWidgetConfig(**w) for w in data.get("widgets", [])])
    except (json.JSONDecodeError, TypeError, ValueError):
        return DashboardLayoutOut(widgets=DEFAULT_WIDGETS)


@router.put("/layout", response_model=DashboardLayoutOut)
async def save_layout(
    body: DashboardLayoutUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    for w in body.widgets:
        if w.metric not in AVAILABLE_METRICS:
            raise HTTPException(status_code=400, detail=f"Unknown metric: {w.metric}")
    payload = json.dumps({"widgets": [w.model_dump() for w in body.widgets]})
    await set_setting(db, _layout_key(user.id), payload)
    await db.commit()
    return DashboardLayoutOut(widgets=body.widgets)
