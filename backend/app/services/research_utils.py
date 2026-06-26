"""Shared helpers for research API and worker."""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import get_settings
from app.schemas.research import ResearchFilters


def parse_research_date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    try:
        if len(raw) == 10:
            dt = datetime.fromisoformat(raw)
            if end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            return dt.replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def filters_to_query_kwargs(filters: ResearchFilters) -> dict:
    direction = filters.direction.strip() if filters.direction else None
    if direction == "":
        direction = None
    queue = filters.queue.strip() if filters.queue else None
    if queue == "":
        queue = None
    tag_id = filters.tag_id
    tag = filters.tag.strip() if filters.tag else None
    if tag == "":
        tag = None
    score_op = filters.score_op.strip() if filters.score_op else None
    if score_op == "":
        score_op = None
    return {
        "date_from": parse_research_date(filters.date_from),
        "date_to": parse_research_date(filters.date_to, end_of_day=True),
        "direction": direction,
        "operator_id": filters.operator_id,
        "queue": queue,
        "tag_id": tag_id,
        "tag": tag,
        "score_op": score_op,
        "score_value": filters.score_value,
    }


def research_max_calls() -> int:
    return get_settings().research_max_calls


def filters_to_json(filters: ResearchFilters) -> dict:
    return filters.model_dump(exclude_none=True)
