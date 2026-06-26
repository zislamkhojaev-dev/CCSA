"""Build SQLAlchemy queries for call list filters and sorting."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import selectinload

from app.models import AnalysisResult, Call, CallTag, Operator


def effective_call_timestamp():
    """Call time for filters/sort when call_timestamp is missing (e.g. playground)."""
    return func.coalesce(Call.call_timestamp, Call.created_at)

SORT_COLUMNS = {
    "id": Call.id,
    "operator_name": Operator.full_name,
    "client_number": Call.client_number,
    "call_timestamp": effective_call_timestamp(),
    "duration": Call.duration,
    "status": Call.status,
    "total_score": AnalysisResult.total_score,
}


def _latest_analysis_join(base: Select) -> Select:
    latest = (
        select(
            AnalysisResult.call_id.label("call_id"),
            func.max(AnalysisResult.created_at).label("max_created"),
        )
        .group_by(AnalysisResult.call_id)
        .subquery()
    )
    return base.outerjoin(latest, latest.c.call_id == Call.id).outerjoin(
        AnalysisResult,
        and_(
            AnalysisResult.call_id == latest.c.call_id,
            AnalysisResult.created_at == latest.c.max_created,
        ),
    )


def _apply_text_filter(
    q: Select,
    column,
    match: str | None,
    value: str | None,
) -> Select:
    if not value or not value.strip():
        return q
    text = value.strip()
    if match == "eq":
        return q.where(column == text)
    return q.where(column.ilike(f"%{text}%"))


def _apply_numeric_filter(q: Select, column, op: str | None, value: int | None) -> Select:
    if value is None or not op:
        return q
    if op == "eq":
        return q.where(column == value)
    if op == "lt":
        return q.where(column < value)
    if op == "gt":
        return q.where(column > value)
    return q


def build_calls_list_query(
    *,
    status_filter: str | None = None,
    operator_match: str | None = None,
    operator_value: str | None = None,
    client_match: str | None = None,
    client_value: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    duration_op: str | None = None,
    duration_value: int | None = None,
    score_op: str | None = None,
    score_value: int | None = None,
    tag_id: int | None = None,
    sort_by: str = "call_timestamp",
    sort_order: str = "desc",
) -> Select:
    q = select(Call).outerjoin(Operator, Call.operator_id == Operator.id)
    needs_score_join = sort_by == "total_score" or score_op is not None
    if needs_score_join:
        q = _latest_analysis_join(q)

    q = _apply_text_filter(q, Operator.full_name, operator_match, operator_value)
    q = _apply_text_filter(q, Call.client_number, client_match, client_value)

    if status_filter:
        q = q.where(Call.status == status_filter)
    call_ts = effective_call_timestamp()
    if date_from:
        q = q.where(call_ts >= date_from)
    if date_to:
        q = q.where(call_ts <= date_to)

    q = _apply_numeric_filter(q, Call.duration, duration_op, duration_value)

    if score_op and score_value is not None:
        if score_op == "eq":
            q = q.where(AnalysisResult.total_score == score_value)
        elif score_op == "lt":
            q = q.where(AnalysisResult.total_score < score_value)
        elif score_op == "gt":
            q = q.where(AnalysisResult.total_score > score_value)

    if tag_id is not None:
        q = q.where(
            Call.id.in_(select(CallTag.call_id).where(CallTag.tag_id == tag_id))
        )

    sort_col = SORT_COLUMNS.get(sort_by, Call.call_timestamp)
    if sort_order == "asc":
        q = q.order_by(sort_col.asc().nullslast(), Call.id.asc())
    else:
        q = q.order_by(sort_col.desc().nullslast(), Call.id.desc())

    return q.options(selectinload(Call.operator))


def build_calls_count_query(
    *,
    status_filter: str | None = None,
    operator_match: str | None = None,
    operator_value: str | None = None,
    client_match: str | None = None,
    client_value: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    duration_op: str | None = None,
    duration_value: int | None = None,
    score_op: str | None = None,
    score_value: int | None = None,
    tag_id: int | None = None,
) -> Select:
    q = select(func.count(func.distinct(Call.id))).select_from(Call).outerjoin(
        Operator, Call.operator_id == Operator.id
    )
    if score_op is not None:
        q = _latest_analysis_join(q)

    q = _apply_text_filter(q, Operator.full_name, operator_match, operator_value)
    q = _apply_text_filter(q, Call.client_number, client_match, client_value)

    if status_filter:
        q = q.where(Call.status == status_filter)
    call_ts = effective_call_timestamp()
    if date_from:
        q = q.where(call_ts >= date_from)
    if date_to:
        q = q.where(call_ts <= date_to)

    q = _apply_numeric_filter(q, Call.duration, duration_op, duration_value)

    if score_op and score_value is not None:
        if score_op == "eq":
            q = q.where(AnalysisResult.total_score == score_value)
        elif score_op == "lt":
            q = q.where(AnalysisResult.total_score < score_value)
        elif score_op == "gt":
            q = q.where(AnalysisResult.total_score > score_value)

    if tag_id is not None:
        q = q.where(
            Call.id.in_(select(CallTag.call_id).where(CallTag.tag_id == tag_id))
        )

    return q
