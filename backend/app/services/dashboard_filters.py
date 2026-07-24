"""Shared date/direction/operator filters for dashboard metrics and export."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select

from app.models import Call
from app.services.call_query import effective_call_timestamp

VALID_DIRECTIONS = frozenset({"inbound", "outbound"})


@dataclass(frozen=True)
class DashboardFilters:
    period_days: int = 30
    date_from: datetime | None = None
    date_to: datetime | None = None
    direction: str | None = None
    operator_ids: tuple[int, ...] = ()

    def time_bounds(self) -> tuple[datetime, datetime | None]:
        now = datetime.now(UTC)
        if self.date_from is not None or self.date_to is not None:
            since = self.date_from or (now - timedelta(days=max(1, self.period_days)))
            until = self.date_to
            return since, until
        since = now - timedelta(days=max(1, self.period_days))
        return since, None

    def to_dict(self) -> dict:
        since, until = self.time_bounds()
        return {
            "period_days": self.period_days,
            "date_from": self.date_from.date().isoformat() if self.date_from else None,
            "date_to": self.date_to.date().isoformat() if self.date_to else None,
            "direction": self.direction,
            "operator_ids": list(self.operator_ids),
            "effective_since": since.isoformat(),
            "effective_until": until.isoformat() if until else None,
        }


def _parse_date_start(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    d = date.fromisoformat(value.strip())
    return datetime.combine(d, time.min, tzinfo=UTC)


def _parse_date_end(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    d = date.fromisoformat(value.strip())
    return datetime.combine(d, time(23, 59, 59), tzinfo=UTC)


def parse_dashboard_filters(
    *,
    period_days: int = 30,
    date_from: str | None = None,
    date_to: str | None = None,
    direction: str | None = None,
    operator_ids: list[int] | None = None,
) -> DashboardFilters:
    parsed_from = _parse_date_start(date_from)
    parsed_to = _parse_date_end(date_to)
    if parsed_from and parsed_to and parsed_from > parsed_to:
        parsed_from, parsed_to = parsed_to, parsed_from

    dir_norm = direction.strip() if direction else None
    if dir_norm == "":
        dir_norm = None
    if dir_norm is not None and dir_norm not in VALID_DIRECTIONS:
        dir_norm = None

    op_ids: tuple[int, ...] = ()
    if operator_ids:
        op_ids = tuple(sorted({i for i in operator_ids if i > 0}))

    return DashboardFilters(
        period_days=max(1, min(365, period_days)),
        date_from=parsed_from,
        date_to=parsed_to,
        direction=dir_norm,
        operator_ids=op_ids,
    )


def apply_call_filters(q: Select, filters: DashboardFilters) -> Select:
    ts = effective_call_timestamp()
    since, until = filters.time_bounds()
    q = q.where(ts >= since)
    if until is not None:
        q = q.where(ts <= until)
    if filters.direction:
        q = q.where(Call.direction == filters.direction)
    if filters.operator_ids:
        q = q.where(Call.operator_id.in_(filters.operator_ids))
    return q


def apply_call_filters_extra(q: Select, filters: DashboardFilters, *, since: datetime | None = None) -> Select:
    """Apply filters with an optional extra lower bound (e.g. start of today)."""
    ts = effective_call_timestamp()
    since_eff, until = filters.time_bounds()
    if since is not None and since > since_eff:
        since_eff = since
    q = q.where(ts >= since_eff)
    if until is not None:
        q = q.where(ts <= until)
    if filters.direction:
        q = q.where(Call.direction == filters.direction)
    if filters.operator_ids:
        q = q.where(Call.operator_id.in_(filters.operator_ids))
    return q
