"""Export dashboard widget metrics with applied filters."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Scenario
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
        "widget_width": widget.width,
        "widget_height": widget.height,
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


def _format_period_label(filters: DashboardFilters) -> str:
    if filters.date_from is not None or filters.date_to is not None:
        since, until = filters.time_bounds()
        start = since.date().isoformat()
        end = until.date().isoformat() if until else "…"
        return f"Свой период: {start} — {end}"
    return f"{filters.period_days} дней"


async def _resolve_scenario_name(db: AsyncSession, scenario_id: int | None) -> str | None:
    if not scenario_id:
        return None
    name = await db.scalar(select(Scenario.name).where(Scenario.id == scenario_id))
    return name


def build_filter_summary(
    filters: DashboardFilters,
    *,
    scenario_name: str | None = None,
) -> dict[str, Any]:
    """Human-readable filter description for export files.

    Only period and scenario — the filters exposed in the dashboard UI.
    """
    period_label = _format_period_label(filters)
    if scenario_name:
        scenario_label = scenario_name
    elif filters.scenario_id:
        scenario_label = f"Сценарий #{filters.scenario_id}"
    else:
        scenario_label = "Все сценарии"

    since, until = filters.time_bounds()
    return {
        "period": period_label,
        "scenario": scenario_label,
        "effective_since": since.isoformat(),
        "effective_until": until.isoformat() if until else None,
        "labels": [
            {"key": "period", "label": "Период", "value": period_label},
            {"key": "scenario", "label": "Сценарий", "value": scenario_label},
        ],
    }


async def build_dashboard_export(
    db: AsyncSession,
    widgets: list[DashboardWidgetConfig],
    filters: DashboardFilters,
    quality: QualityConfig | None = None,
) -> dict[str, Any]:
    scenario_name = await _resolve_scenario_name(db, filters.scenario_id)
    metrics: list[dict[str, Any]] = []
    for widget in widgets:
        data = await fetch_widget_metric(db, widget.metric, filters, quality)
        metrics.append(_metric_to_dict(widget, data))
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "filters": filters.to_dict(),
        "filter_summary": build_filter_summary(filters, scenario_name=scenario_name),
        "widgets": metrics,
    }


def _csv_filter_preamble(payload: dict[str, Any]) -> list[str]:
    """Comment lines describing export filters (skipped by most CSV tools)."""
    lines = [
        f"# CCSA dashboard export",
        f"# exported_at: {payload.get('exported_at', '')}",
    ]
    summary = payload.get("filter_summary") or {}
    for item in summary.get("labels") or []:
        label = item.get("label") or ""
        value = item.get("value") or ""
        lines.append(f"# {label}: {value}")
    if summary.get("effective_since"):
        lines.append(f"# Дата с (эфф.): {summary['effective_since']}")
    if summary.get("effective_until"):
        lines.append(f"# Дата по (эфф.): {summary['effective_until']}")
    lines.append("#")
    return lines


def dashboard_export_to_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    for line in _csv_filter_preamble(payload):
        buf.write(line + "\n")

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
