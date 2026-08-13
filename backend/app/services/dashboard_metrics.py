"""Aggregate call, score, duration, and operator metrics for dashboard widgets."""

from datetime import UTC, datetime

from sqlalchemy import Date, case, cast, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisResult, Call, Criterion, Operator, Transcription
from app.schemas.dashboard import MetricSeriesPoint, WidgetMetricResponse
from app.services.call_utils import duration_seconds_from_utterances
from app.services.call_query import effective_call_timestamp
from app.services.dashboard_filters import DashboardFilters, apply_call_filters, apply_call_filters_extra
from app.services.quality_settings import UNCLASSIFIED_TOPIC, QualityConfig

METRIC_LABELS: dict[str, str] = {
    "calls_total": "Всего звонков",
    "calls_today": "Звонков сегодня",
    "calls_analyzed": "Проанализировано",
    "calls_pending": "В очереди",
    "score_avg": "Средний балл",
    "score_distribution": "Распределение оценок",
    "violations_count": "Нарушения",
    "percent_analyzed": "Доля проанализированных",
    "percent_violations": "Доля нарушений",
    "percent_high_score": "Доля оценок >80%",
    "duration_avg": "Средняя длительность",
    "duration_total": "Суммарная длительность",
    "duration_distribution": "Распределение длительности",
    "calls_by_day": "Звонки по дням",
    "operators_by_calls": "Топ операторов по звонкам",
    "operators_by_score": "Топ операторов по баллу",
    "comparison_calls_analyzed": "Звонки vs проанализировано",
    "comparison_score_violations": "Средний балл vs нарушения",
    "coverage": "Покрытие оценкой",
    "criteria_pass_rate": "Проседающие критерии",
    "score_by_day": "Динамика среднего балла",
    "operators_top_best": "Топ-5 лучших операторов",
    "operators_top_worst": "Топ-5 худших операторов",
    "topics_distribution": "Классификация тем",
    "score_by_topic": "Качество по темам",
    "criteria_operator_heatmap": "Критерии × операторы",
    "calls_heatmap_hour_day": "Пиковые часы (час × день)",
}

WEEKDAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {sec}с"
    return f"{sec}с"


async def _call_durations_in_period(db: AsyncSession, filters: DashboardFilters) -> list[int]:
    """Collect effective durations (Call.duration or latest transcription utterances)."""
    latest_trans = (
        select(
            Transcription.call_id.label("call_id"),
            func.max(Transcription.id).label("transcription_id"),
        )
        .group_by(Transcription.call_id)
        .subquery()
    )
    q = (
        select(Call.duration, Transcription.utterances)
        .select_from(Call)
        .outerjoin(latest_trans, latest_trans.c.call_id == Call.id)
        .outerjoin(Transcription, Transcription.id == latest_trans.c.transcription_id)
    )
    q = apply_call_filters(q, filters)
    result = await db.execute(q)
    durations: list[int] = []
    for call_duration, utterances in result.all():
        if call_duration is not None:
            durations.append(int(call_duration))
            continue
        derived = duration_seconds_from_utterances(utterances)
        if derived is not None:
            durations.append(derived)
    return durations


async def _criterion_name_map(db: AsyncSession, scenario_id: int | None = None) -> dict[str, str]:
    q = select(Criterion.key, Criterion.name)
    if scenario_id:
        q = q.where(Criterion.scenario_id == scenario_id)
    result = await db.execute(q)
    mapping: dict[str, str] = {}
    for key, name in result.all():
        if key:
            mapping[key] = name or key
    return mapping


def _criteria_lateral():
    return (
        func.jsonb_each(AnalysisResult.criteria_results)
        .table_valued("key", "value")
        .lateral()
        .alias("crit")
    )


def _criteria_applicable(crit):
    status_text = func.coalesce(crit.c.value["status"].astext, "")
    return status_text != "not_applicable"


async def _criteria_pass_rows(db: AsyncSession, filters: DashboardFilters) -> list[tuple]:
    crit = _criteria_lateral()
    passed_expr = case((crit.c.value["passed"].astext == "true", 1), else_=0)
    q = (
        select(
            crit.c.key.label("key"),
            func.count().label("total"),
            func.sum(passed_expr).label("passed"),
        )
        .select_from(AnalysisResult)
        .join(Call, Call.id == AnalysisResult.call_id)
        .join(crit, true())
        .where(_criteria_applicable(crit))
    )
    q = apply_call_filters(q, filters).group_by(crit.c.key)
    result = await db.execute(q)
    return list(result.all())


async def _criteria_operator_rows(db: AsyncSession, filters: DashboardFilters) -> list[tuple]:
    crit = _criteria_lateral()
    passed_expr = case((crit.c.value["passed"].astext == "true", 1), else_=0)
    q = (
        select(
            crit.c.key.label("key"),
            Operator.full_name.label("operator_name"),
            func.count().label("total"),
            func.sum(passed_expr).label("passed"),
        )
        .select_from(AnalysisResult)
        .join(Call, Call.id == AnalysisResult.call_id)
        .outerjoin(Operator, Operator.id == Call.operator_id)
        .join(crit, true())
        .where(_criteria_applicable(crit))
    )
    q = apply_call_filters(q, filters).group_by(crit.c.key, Operator.full_name)
    result = await db.execute(q)
    return list(result.all())


async def fetch_widget_metric(
    db: AsyncSession,
    metric: str,
    filters: DashboardFilters | None = None,
    quality: QualityConfig | None = None,
) -> WidgetMetricResponse:
    filters = filters or DashboardFilters()
    quality = quality or QualityConfig()
    good = quality.threshold_good
    mid = quality.threshold_mid
    label = METRIC_LABELS.get(metric, metric)
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    if metric == "calls_total":
        q = select(func.count()).select_from(Call)
        q = apply_call_filters(q, filters)
        val = await db.scalar(q) or 0
        return WidgetMetricResponse(
            metric=metric, kind="scalar", label=label, value=float(val), formatted=str(val), unit="шт"
        )

    if metric == "calls_today":
        q = select(func.count()).select_from(Call)
        q = apply_call_filters_extra(q, filters, since=today_start)
        val = await db.scalar(q) or 0
        return WidgetMetricResponse(
            metric=metric, kind="scalar", label=label, value=float(val), formatted=str(val), unit="шт"
        )

    if metric == "calls_analyzed":
        q = select(func.count()).select_from(Call).where(Call.status == "analyzed")
        q = apply_call_filters(q, filters)
        val = await db.scalar(q) or 0
        return WidgetMetricResponse(
            metric=metric, kind="scalar", label=label, value=float(val), formatted=str(val), unit="шт"
        )

    if metric == "calls_pending":
        q = (
            select(func.count())
            .select_from(Call)
            .where(Call.status.not_in(["analyzed", "error"]))
        )
        q = apply_call_filters(q, filters)
        val = await db.scalar(q) or 0
        return WidgetMetricResponse(
            metric=metric, kind="scalar", label=label, value=float(val), formatted=str(val), unit="шт"
        )

    if metric == "violations_count":
        q = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(AnalysisResult.is_violation.is_(True))
        )
        q = apply_call_filters(q, filters)
        val = await db.scalar(q) or 0
        return WidgetMetricResponse(
            metric=metric, kind="scalar", label=label, value=float(val), formatted=str(val), unit="шт"
        )

    if metric == "score_avg":
        q = (
            select(func.avg(AnalysisResult.total_score))
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
        )
        q = apply_call_filters(q, filters)
        avg = await db.scalar(q)
        val = round(float(avg), 1) if avg else None
        return WidgetMetricResponse(
            metric=metric,
            kind="scalar",
            label=label,
            value=val,
            formatted=f"{val}%" if val is not None else "—",
            unit="%",
            stats={"min": None, "max": None},
        )

    if metric == "duration_avg":
        durations = await _call_durations_in_period(db, filters)
        val = round(sum(durations) / len(durations), 1) if durations else None
        return WidgetMetricResponse(
            metric=metric,
            kind="stat",
            label=label,
            value=val,
            formatted=_format_duration(val),
            unit="сек",
            stats={"avg_seconds": val},
        )

    if metric == "duration_total":
        durations = await _call_durations_in_period(db, filters)
        val = float(sum(durations)) if durations else 0
        return WidgetMetricResponse(
            metric=metric,
            kind="stat",
            label=label,
            value=val,
            formatted=_format_duration(val),
            unit="сек",
        )

    if metric == "percent_analyzed":
        q_total = select(func.count()).select_from(Call)
        q_total = apply_call_filters(q_total, filters)
        total = await db.scalar(q_total) or 0
        q_analyzed = select(func.count()).select_from(Call).where(Call.status == "analyzed")
        q_analyzed = apply_call_filters(q_analyzed, filters)
        analyzed = await db.scalar(q_analyzed) or 0
        pct = round(analyzed / total * 100, 1) if total else 0
        return WidgetMetricResponse(
            metric=metric,
            kind="percent",
            label=label,
            value=pct,
            formatted=f"{pct}%",
            unit="%",
            comparison={"numerator": analyzed, "denominator": total},
        )

    if metric == "percent_violations":
        q_analyzed = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
        )
        q_analyzed = apply_call_filters(q_analyzed, filters)
        analyzed = await db.scalar(q_analyzed) or 0
        q_violations = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(AnalysisResult.is_violation.is_(True))
        )
        q_violations = apply_call_filters(q_violations, filters)
        violations = await db.scalar(q_violations) or 0
        pct = round(violations / analyzed * 100, 1) if analyzed else 0
        return WidgetMetricResponse(
            metric=metric,
            kind="percent",
            label=label,
            value=pct,
            formatted=f"{pct}%",
            unit="%",
            comparison={"numerator": violations, "denominator": analyzed},
        )

    if metric == "percent_high_score":
        q_total = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
        )
        q_total = apply_call_filters(q_total, filters)
        total = await db.scalar(q_total) or 0
        q_high = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(AnalysisResult.total_score >= good)
        )
        q_high = apply_call_filters(q_high, filters)
        high = await db.scalar(q_high) or 0
        pct = round(high / total * 100, 1) if total else 0
        return WidgetMetricResponse(
            metric=metric,
            kind="percent",
            label=label,
            value=pct,
            formatted=f"{pct}%",
            unit="%",
            comparison={"numerator": high, "denominator": total},
        )

    if metric == "score_distribution":
        q_green = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(AnalysisResult.total_score >= good)
        )
        q_green = apply_call_filters(q_green, filters)
        green = await db.scalar(q_green) or 0
        q_yellow = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(
                AnalysisResult.total_score >= mid,
                AnalysisResult.total_score < good,
            )
        )
        q_yellow = apply_call_filters(q_yellow, filters)
        yellow = await db.scalar(q_yellow) or 0
        q_red = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(AnalysisResult.total_score < mid)
        )
        q_red = apply_call_filters(q_red, filters)
        red = await db.scalar(q_red) or 0
        series = [
            MetricSeriesPoint(label=f"≥{good}%", value=float(green)),
            MetricSeriesPoint(label=f"{mid}–{good}%", value=float(yellow)),
            MetricSeriesPoint(label=f"<{mid}%", value=float(red)),
        ]
        return WidgetMetricResponse(metric=metric, kind="series", label=label, series=series)

    if metric == "duration_distribution":
        buckets = [
            ("< 1 мин", 0, 60),
            ("1–3 мин", 60, 180),
            ("3–5 мин", 180, 300),
            ("> 5 мин", 300, None),
        ]
        durations = await _call_durations_in_period(db, filters)
        series: list[MetricSeriesPoint] = []
        for lbl, lo, hi in buckets:
            cnt = sum(1 for d in durations if d >= lo and (hi is None or d < hi))
            series.append(MetricSeriesPoint(label=lbl, value=float(cnt)))
        return WidgetMetricResponse(metric=metric, kind="series", label=label, series=series)

    if metric == "calls_by_day":
        day_col = cast(func.date_trunc("day", effective_call_timestamp()), Date)
        q = select(day_col.label("day"), func.count().label("cnt")).select_from(Call)
        q = apply_call_filters(q, filters)
        q = q.group_by(day_col).order_by(day_col)
        result = await db.execute(q)
        series = [
            MetricSeriesPoint(label=row.day.strftime("%d.%m") if row.day else "?", value=float(row.cnt))
            for row in result.all()
        ]
        return WidgetMetricResponse(metric=metric, kind="series", label=label, series=series)

    if metric == "operators_by_calls":
        q = (
            select(Operator.full_name, func.count(Call.id).label("cnt"))
            .select_from(Operator)
            .join(Call, Call.operator_id == Operator.id)
        )
        q = apply_call_filters(q, filters)
        q = q.group_by(Operator.id, Operator.full_name).order_by(func.count(Call.id).desc()).limit(8)
        result = await db.execute(q)
        series = [MetricSeriesPoint(label=row.full_name, value=float(row.cnt or 0)) for row in result.all()]
        return WidgetMetricResponse(metric=metric, kind="series", label=label, series=series)

    if metric == "operators_by_score":
        q = (
            select(Operator.full_name, func.avg(AnalysisResult.total_score).label("avg"))
            .select_from(Operator)
            .join(Call, Call.operator_id == Operator.id)
            .join(AnalysisResult, AnalysisResult.call_id == Call.id)
        )
        q = apply_call_filters(q, filters)
        q = (
            q.group_by(Operator.id, Operator.full_name)
            .having(func.count(AnalysisResult.id) > 0)
            .order_by(func.avg(AnalysisResult.total_score).desc())
            .limit(8)
        )
        result = await db.execute(q)
        series = [
            MetricSeriesPoint(
                label=row.full_name,
                value=round(float(row.avg), 1) if row.avg else 0,
            )
            for row in result.all()
        ]
        return WidgetMetricResponse(metric=metric, kind="series", label=label, series=series, unit="%")

    if metric == "comparison_calls_analyzed":
        q_total = select(func.count()).select_from(Call)
        q_total = apply_call_filters(q_total, filters)
        total = await db.scalar(q_total) or 0
        q_analyzed = select(func.count()).select_from(Call).where(Call.status == "analyzed")
        q_analyzed = apply_call_filters(q_analyzed, filters)
        analyzed = await db.scalar(q_analyzed) or 0
        return WidgetMetricResponse(
            metric=metric,
            kind="comparison",
            label=label,
            comparison={
                "left": {"label": "Всего звонков", "value": total},
                "right": {"label": "Проанализировано", "value": analyzed},
                "delta": analyzed - total if total else 0,
            },
            series=[
                MetricSeriesPoint(label="Всего", value=float(total)),
                MetricSeriesPoint(label="Проанализировано", value=float(analyzed)),
            ],
        )

    if metric == "comparison_score_violations":
        q_avg = (
            select(func.avg(AnalysisResult.total_score))
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
        )
        q_avg = apply_call_filters(q_avg, filters)
        avg = await db.scalar(q_avg)
        q_violations = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(AnalysisResult.is_violation.is_(True))
        )
        q_violations = apply_call_filters(q_violations, filters)
        violations = await db.scalar(q_violations) or 0
        avg_val = round(float(avg), 1) if avg else 0
        return WidgetMetricResponse(
            metric=metric,
            kind="comparison",
            label=label,
            comparison={
                "left": {"label": "Средний балл", "value": avg_val, "unit": "%"},
                "right": {"label": "Нарушения", "value": violations, "unit": "шт"},
            },
            series=[
                MetricSeriesPoint(label="Средний балл", value=avg_val),
                MetricSeriesPoint(label="Нарушения", value=float(violations)),
            ],
        )

    if metric == "coverage":
        q_total = select(func.count()).select_from(Call)
        q_total = apply_call_filters(q_total, filters)
        total = await db.scalar(q_total) or 0
        q_scored = (
            select(func.count(func.distinct(AnalysisResult.call_id)))
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
        )
        q_scored = apply_call_filters(q_scored, filters)
        scored = await db.scalar(q_scored) or 0
        pct = round(scored / total * 100, 1) if total else 0
        return WidgetMetricResponse(
            metric=metric,
            kind="percent",
            label=label,
            value=pct,
            formatted=f"{pct}%",
            unit="%",
            comparison={"numerator": scored, "denominator": total},
        )

    if metric == "criteria_pass_rate":
        rows = await _criteria_pass_rows(db, filters)
        name_map = await _criterion_name_map(db, filters.scenario_id)
        items = [
            (row.key, round((row.passed or 0) / row.total * 100, 1), int(row.total))
            for row in rows
            if row.total
        ]
        items.sort(key=lambda x: x[1])  # worst first
        series = [
            MetricSeriesPoint(label=name_map.get(key, key), value=rate, value_secondary=float(n))
            for key, rate, n in items[:12]
        ]
        return WidgetMetricResponse(metric=metric, kind="series", label=label, series=series, unit="%")

    if metric == "score_by_day":
        day_col = cast(func.date_trunc("day", effective_call_timestamp()), Date)
        q = (
            select(day_col.label("day"), func.avg(AnalysisResult.total_score).label("avg"))
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
        )
        q = apply_call_filters(q, filters)
        q = q.group_by(day_col).order_by(day_col)
        result = await db.execute(q)
        series = [
            MetricSeriesPoint(
                label=row.day.strftime("%d.%m") if row.day else "?",
                value=round(float(row.avg), 1) if row.avg is not None else 0.0,
            )
            for row in result.all()
        ]
        return WidgetMetricResponse(
            metric=metric, kind="series", label=label, series=series, unit="%", target=float(quality.target)
        )

    if metric in ("operators_top_best", "operators_top_worst"):
        q = (
            select(
                Operator.full_name,
                func.avg(AnalysisResult.total_score).label("avg"),
                func.count(AnalysisResult.id).label("cnt"),
            )
            .select_from(Operator)
            .join(Call, Call.operator_id == Operator.id)
            .join(AnalysisResult, AnalysisResult.call_id == Call.id)
        )
        q = apply_call_filters(q, filters)
        order = func.avg(AnalysisResult.total_score)
        q = q.group_by(Operator.id, Operator.full_name).having(func.count(AnalysisResult.id) > 0)
        q = q.order_by(order.desc() if metric == "operators_top_best" else order.asc()).limit(5)
        result = await db.execute(q)
        series = [
            MetricSeriesPoint(
                label=row.full_name,
                value=round(float(row.avg), 1) if row.avg is not None else 0.0,
                value_secondary=float(row.cnt or 0),
            )
            for row in result.all()
        ]
        return WidgetMetricResponse(metric=metric, kind="series", label=label, series=series, unit="%")

    if metric == "topics_distribution":
        topic_expr = func.coalesce(AnalysisResult.topic, UNCLASSIFIED_TOPIC)
        q = (
            select(topic_expr.label("topic"), func.count().label("cnt"))
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
        )
        q = apply_call_filters(q, filters)
        q = q.group_by(topic_expr).order_by(func.count().desc()).limit(20)
        result = await db.execute(q)
        series = [MetricSeriesPoint(label=row.topic, value=float(row.cnt)) for row in result.all()]
        return WidgetMetricResponse(metric=metric, kind="series", label=label, series=series)

    if metric == "score_by_topic":
        topic_expr = func.coalesce(AnalysisResult.topic, UNCLASSIFIED_TOPIC)
        q = (
            select(
                topic_expr.label("topic"),
                func.avg(AnalysisResult.total_score).label("avg"),
                func.count().label("cnt"),
            )
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
        )
        q = apply_call_filters(q, filters)
        q = q.group_by(topic_expr).order_by(func.avg(AnalysisResult.total_score).asc()).limit(20)
        result = await db.execute(q)
        series = [
            MetricSeriesPoint(
                label=row.topic,
                value=round(float(row.avg), 1) if row.avg is not None else 0.0,
                value_secondary=float(row.cnt or 0),
            )
            for row in result.all()
        ]
        return WidgetMetricResponse(metric=metric, kind="series", label=label, series=series, unit="%")

    if metric == "criteria_operator_heatmap":
        rows = await _criteria_operator_rows(db, filters)
        name_map = await _criterion_name_map(db, filters.scenario_id)
        cell: dict[tuple[str, str], list[int]] = {}
        crit_total: dict[str, int] = {}
        op_total: dict[str, int] = {}
        for row in rows:
            operator = row.operator_name or "Без оператора"
            key = row.key
            total_n = int(row.total or 0)
            passed_n = int(row.passed or 0)
            if not key or total_n <= 0:
                continue
            cell[(key, operator)] = [passed_n, total_n]
            crit_total[key] = crit_total.get(key, 0) + total_n
            op_total[operator] = op_total.get(operator, 0) + total_n
        # worst criteria first, busiest operators first
        crit_keys = sorted(crit_total, key=lambda k: crit_total[k], reverse=True)[:12]
        crit_keys.sort(
            key=lambda k: (
                sum(cell.get((k, o), [0, 0])[0] for o in op_total)
                / max(1, sum(cell.get((k, o), [0, 0])[1] for o in op_total))
            )
        )
        op_names = sorted(op_total, key=lambda o: op_total[o], reverse=True)[:12]
        cells = []
        for key in crit_keys:
            row_cells = []
            for op in op_names:
                pv = cell.get((key, op))
                if pv and pv[1] > 0:
                    row_cells.append({"value": round(pv[0] / pv[1] * 100, 1), "count": pv[1]})
                else:
                    row_cells.append(None)
            cells.append(row_cells)
        matrix = {
            "rows": [{"key": k, "label": name_map.get(k, k)} for k in crit_keys],
            "cols": [{"label": o} for o in op_names],
            "cells": cells,
            "unit": "%",
        }
        return WidgetMetricResponse(metric=metric, kind="matrix", label=label, matrix=matrix)

    if metric == "calls_heatmap_hour_day":
        ts = effective_call_timestamp()
        dow = func.extract("dow", ts)  # 0=Sunday..6=Saturday
        hour = func.extract("hour", ts)
        q = select(dow.label("dow"), hour.label("hour"), func.count().label("cnt")).select_from(Call)
        q = apply_call_filters(q, filters)
        q = q.group_by(dow, hour)
        result = await db.execute(q)
        grid = [[0 for _ in range(24)] for _ in range(7)]
        for row in result.all():
            # Convert Postgres dow (0=Sun) to Mon-first index (0=Mon..6=Sun)
            pg_dow = int(row.dow)
            idx = (pg_dow + 6) % 7
            h = int(row.hour)
            if 0 <= h < 24:
                grid[idx][h] = int(row.cnt)
        matrix = {
            "rows": [{"label": WEEKDAY_LABELS[i]} for i in range(7)],
            "cols": [{"label": f"{h:02d}"} for h in range(24)],
            "cells": [[{"value": grid[i][h]} for h in range(24)] for i in range(7)],
            "unit": "шт",
        }
        return WidgetMetricResponse(metric=metric, kind="matrix", label=label, matrix=matrix)

    return WidgetMetricResponse(
        metric=metric,
        kind="scalar",
        label=label,
        value=None,
        formatted="—",
    )


AVAILABLE_METRICS = list(METRIC_LABELS.keys())
