"""Select calls with transcriptions for LLM cohort research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import aliased

from app.models import AnalysisResult, Call, CallTag, Operator, Tag, Transcription
from app.services.call_query import effective_call_timestamp


@dataclass(frozen=True)
class CohortCallRow:
    call_id: int
    call_timestamp: datetime | None
    direction: str | None
    duration: int | None
    operator_name: str | None
    full_text: str


def _latest_transcription_subquery():
    latest = (
        select(
            Transcription.call_id.label("call_id"),
            func.max(Transcription.created_at).label("max_created"),
        )
        .group_by(Transcription.call_id)
        .subquery()
    )
    t = aliased(Transcription)
    return (
        select(t)
        .join(
            latest,
            and_(
                t.call_id == latest.c.call_id,
                t.created_at == latest.c.max_created,
            ),
        )
        .where(t.full_text.isnot(None))
        .where(func.length(func.trim(t.full_text)) > 0)
        .subquery()
    )


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


def _apply_research_filters(
    q: Select,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    direction: str | None = None,
    operator_id: int | None = None,
    queue: str | None = None,
    tag_id: int | None = None,
    tag: str | None = None,
    score_op: str | None = None,
    score_value: int | None = None,
) -> Select:
    call_ts = effective_call_timestamp()
    if date_from:
        q = q.where(call_ts >= date_from)
    if date_to:
        q = q.where(call_ts <= date_to)
    if direction:
        q = q.where(Call.direction == direction)
    if operator_id is not None:
        q = q.where(Call.operator_id == operator_id)
    if queue:
        q = q.where(Operator.team_name == queue)
    if tag_id is not None:
        q = q.where(
            Call.id.in_(select(CallTag.call_id).where(CallTag.tag_id == tag_id))
        )
    elif tag:
        q = q.where(
            Call.id.in_(
                select(CallTag.call_id)
                .join(Tag, CallTag.tag_id == Tag.id)
                .where(Tag.name == tag)
            )
        )
    if score_op and score_value is not None:
        if score_op == "eq":
            q = q.where(AnalysisResult.total_score == score_value)
        elif score_op == "lt":
            q = q.where(AnalysisResult.total_score < score_value)
        elif score_op == "gt":
            q = q.where(AnalysisResult.total_score > score_value)
    return q


def build_research_calls_query(
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    direction: str | None = None,
    operator_id: int | None = None,
    queue: str | None = None,
    tag_id: int | None = None,
    tag: str | None = None,
    score_op: str | None = None,
    score_value: int | None = None,
) -> Select:
    trans_sq = _latest_transcription_subquery()
    call_ts = effective_call_timestamp()
    q = (
        select(
            Call.id,
            call_ts.label("call_timestamp"),
            Call.direction,
            Call.duration,
            Operator.full_name,
            trans_sq.c.full_text,
        )
        .join(trans_sq, trans_sq.c.call_id == Call.id)
        .outerjoin(Operator, Call.operator_id == Operator.id)
    )
    if score_op is not None:
        q = _latest_analysis_join(q)
    q = _apply_research_filters(
        q,
        date_from=date_from,
        date_to=date_to,
        direction=direction,
        operator_id=operator_id,
        queue=queue,
        tag_id=tag_id,
        tag=tag,
        score_op=score_op,
        score_value=score_value,
    )
    return q.order_by(call_ts.desc(), Call.id.desc())


def build_research_count_query(
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    direction: str | None = None,
    operator_id: int | None = None,
    queue: str | None = None,
    tag_id: int | None = None,
    tag: str | None = None,
    score_op: str | None = None,
    score_value: int | None = None,
) -> Select:
    trans_sq = _latest_transcription_subquery()
    q = (
        select(func.count(func.distinct(Call.id)))
        .select_from(Call)
        .join(trans_sq, trans_sq.c.call_id == Call.id)
        .outerjoin(Operator, Call.operator_id == Operator.id)
    )
    if score_op is not None:
        q = _latest_analysis_join(q)
    q = _apply_research_filters(
        q,
        date_from=date_from,
        date_to=date_to,
        direction=direction,
        operator_id=operator_id,
        queue=queue,
        tag_id=tag_id,
        tag=tag,
        score_op=score_op,
        score_value=score_value,
    )
    return q


def build_research_calls_by_ids_query(call_ids: list[int]) -> Select:
    """Load cohort rows for a snapshot of call ids (fixed at study creation)."""
    if not call_ids:
        return build_research_calls_query().where(Call.id == -1)

    trans_sq = _latest_transcription_subquery()
    call_ts = effective_call_timestamp()
    return (
        select(
            Call.id,
            call_ts.label("call_timestamp"),
            Call.direction,
            Call.duration,
            Operator.full_name,
            trans_sq.c.full_text,
        )
        .join(trans_sq, trans_sq.c.call_id == Call.id)
        .outerjoin(Operator, Call.operator_id == Operator.id)
        .where(Call.id.in_(call_ids))
        .order_by(call_ts.desc(), Call.id.desc())
    )
