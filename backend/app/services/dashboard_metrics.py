"""Aggregate call, score, duration, and operator metrics for dashboard widgets."""

from datetime import UTC, datetime

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisResult, Call, Operator, Transcription
from app.schemas.dashboard import MetricSeriesPoint, WidgetMetricResponse
from app.services.call_utils import duration_seconds_from_utterances
from app.services.call_query import effective_call_timestamp
from app.services.dashboard_filters import DashboardFilters, apply_call_filters, apply_call_filters_extra

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
}


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


async def fetch_widget_metric(
    db: AsyncSession, metric: str, filters: DashboardFilters | None = None
) -> WidgetMetricResponse:
    filters = filters or DashboardFilters()
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
            .where(AnalysisResult.total_score >= 80)
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
            .where(AnalysisResult.total_score >= 80)
        )
        q_green = apply_call_filters(q_green, filters)
        green = await db.scalar(q_green) or 0
        q_yellow = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(
                AnalysisResult.total_score >= 50,
                AnalysisResult.total_score < 80,
            )
        )
        q_yellow = apply_call_filters(q_yellow, filters)
        yellow = await db.scalar(q_yellow) or 0
        q_red = (
            select(func.count())
            .select_from(AnalysisResult)
            .join(Call, Call.id == AnalysisResult.call_id)
            .where(AnalysisResult.total_score < 50)
        )
        q_red = apply_call_filters(q_red, filters)
        red = await db.scalar(q_red) or 0
        series = [
            MetricSeriesPoint(label=">80%", value=float(green)),
            MetricSeriesPoint(label="50-80%", value=float(yellow)),
            MetricSeriesPoint(label="<50%", value=float(red)),
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

    return WidgetMetricResponse(
        metric=metric,
        kind="scalar",
        label=label,
        value=None,
        formatted="—",
    )


AVAILABLE_METRICS = list(METRIC_LABELS.keys())
