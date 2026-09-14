from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.errors import AppError
from app.database import get_db
from app.models import User
from app.schemas.dashboard import (
    DashboardLayoutOut,
    DashboardLayoutUpdate,
    DashboardSummary,
    WidgetMetricResponse,
    WidgetMetricsBatchIn,
    WidgetMetricsBatchOut,
)
from app.services.dashboard_export import (
    build_dashboard_export,
    dashboard_export_filename,
    dashboard_export_json_bytes,
    dashboard_export_to_csv,
)
from app.services.dashboard_filters import parse_dashboard_filters
from app.services.dashboard_metrics import AVAILABLE_METRICS, fetch_widget_metric
from app.services.dashboard_service import dashboard_service
from app.services.feature_flags import require_feature
from app.services.quality_settings import load_quality_config

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
async def summary(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await dashboard_service.summary(db)


@router.get("/metrics/available", response_model=list[str])
async def list_metrics(_: User = Depends(get_current_user)):
    return AVAILABLE_METRICS


@router.get("/metrics", response_model=WidgetMetricResponse)
async def widget_metric(
    metric: str = Query(..., description="Metric key"),
    period_days: int = Query(30, ge=1, le=365),
    date_from: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    date_to: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    direction: str | None = Query(None, description="inbound | outbound"),
    operator_ids: list[int] | None = Query(None),
    scenario_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if metric not in AVAILABLE_METRICS:
        raise AppError.invalid(f"Unknown metric: {metric}")
    filters = parse_dashboard_filters(
        period_days=period_days,
        date_from=date_from,
        date_to=date_to,
        direction=direction,
        operator_ids=operator_ids,
        scenario_id=scenario_id,
    )
    quality = await load_quality_config(db)
    return await fetch_widget_metric(db, metric, filters, quality)


@router.post("/metrics/batch", response_model=WidgetMetricsBatchOut)
async def widget_metrics_batch(
    body: WidgetMetricsBatchIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    unknown = [m for m in body.metrics if m not in AVAILABLE_METRICS]
    if unknown:
        raise AppError.invalid(f"Unknown metric: {unknown[0]}")
    filters = parse_dashboard_filters(
        period_days=body.period_days,
        date_from=body.date_from,
        date_to=body.date_to,
        direction=body.direction,
        operator_ids=body.operator_ids,
        scenario_id=body.scenario_id,
    )
    quality = await load_quality_config(db)
    items: dict[str, WidgetMetricResponse] = {}
    for metric in dict.fromkeys(body.metrics):
        items[metric] = await fetch_widget_metric(db, metric, filters, quality)
    return WidgetMetricsBatchOut(items=items)


@router.get("/export")
async def export_dashboard(
    format: str = Query("json", pattern="^(json|csv)$"),
    period_days: int = Query(30, ge=1, le=365),
    date_from: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    date_to: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    direction: str | None = Query(None, description="inbound | outbound"),
    operator_ids: list[int] | None = Query(None),
    scenario_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = parse_dashboard_filters(
        period_days=period_days,
        date_from=date_from,
        date_to=date_to,
        direction=direction,
        operator_ids=operator_ids,
        scenario_id=scenario_id,
    )
    widgets = await dashboard_service.load_user_widgets(db, user.id)
    quality = await load_quality_config(db)
    payload = await build_dashboard_export(db, widgets, filters, quality)
    filename = dashboard_export_filename(ext=format)

    if format == "csv":
        content = "\ufeff" + dashboard_export_to_csv(payload)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return Response(
        content=dashboard_export_json_bytes(payload),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/layout", response_model=DashboardLayoutOut)
async def get_layout(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_feature(db, "dashboard_constructor")
    return DashboardLayoutOut(widgets=await dashboard_service.load_user_widgets(db, user.id))


@router.put("/layout", response_model=DashboardLayoutOut)
async def save_layout(
    body: DashboardLayoutUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_feature(db, "dashboard_constructor")
    return await dashboard_service.save_layout(db, user.id, body.widgets)
