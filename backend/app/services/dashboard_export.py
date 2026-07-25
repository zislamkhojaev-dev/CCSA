"""Export dashboard widget metrics with applied filters."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.dashboard import DashboardWidgetConfig, WidgetMetricResponse
from app.services.dashboard_filters import DashboardFilters
from app.services.dashboard_metrics import METRIC_LABELS, fetch_widget_metric
from app.services.quality_settings import QualityConfig


def dashboard_export_filename(*, ext: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return f"dashboard-{stamp}.{ext}"


def _metric_to_dict(widget: DashboardWidgetConfig, data: WidgetMetricResponse) -> dict[str, Any]:
    return {
        "widget_id": widget.id,
        "widget_title": widget.title,
        "widget_type": widget.type,
        "widget_size": widget.size,
        "metric": data.metric,
        "metric_label": METRIC_LABELS.get(data.metric, data.label),
        "kind": data.kind,
        "value": data.value,
        "formatted": data.formatted,
        "unit": data.unit,
        "series": [p.model_dump() for p in data.series],
        "comparison": data.comparison,
        "stats": data.stats,
    }


async def build_dashboard_export(
    db: AsyncSession,
    widgets: list[DashboardWidgetConfig],
    filters: DashboardFilters,
    quality: QualityConfig | None = None,
) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = []
    for widget in widgets:
        data = await fetch_widget_metric(db, widget.metric, filters, quality)
        metrics.append(_metric_to_dict(widget, data))
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "filters": filters.to_dict(),
        "widgets": metrics,
    }


def dashboard_export_to_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "widget_title",
            "metric",
            "metric_label",
            "kind",
            "value",
            "formatted",
            "unit",
            "series_label",
            "series_value",
        ]
    )
    for row in payload.get("widgets", []):
        series = row.get("series") or []
        if series:
            for point in series:
                writer.writerow(
                    [
                        row.get("widget_title"),
                        row.get("metric"),
                        row.get("metric_label"),
                        row.get("kind"),
                        row.get("value"),
                        row.get("formatted"),
                        row.get("unit"),
                        point.get("label"),
                        point.get("value"),
                    ]
                )
        else:
            writer.writerow(
                [
                    row.get("widget_title"),
                    row.get("metric"),
                    row.get("metric_label"),
                    row.get("kind"),
                    row.get("value"),
                    row.get("formatted"),
                    row.get("unit"),
                    "",
                    "",
                ]
            )
    return buf.getvalue()


def dashboard_export_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
