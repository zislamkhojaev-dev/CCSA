import json
from datetime import datetime

from croniter import croniter


def is_within_sync_window(
    *,
    active_days: list[int] | None,
    time_from: str | None,
    time_to: str | None,
    now: datetime | None = None,
) -> bool:
    """Check weekday (0=Mon) and HH:MM window for Webitel/automation."""
    now = now or datetime.now()
    days = active_days if active_days is not None else [0, 1, 2, 3, 4]
    if days and now.weekday() not in days:
        return False
    if not time_from or not time_to:
        return True
    try:
        start_h, start_m = map(int, time_from.split(":"))
        end_h, end_m = map(int, time_to.split(":"))
        current = now.hour * 60 + now.minute
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end
    except ValueError:
        return True


def parse_sync_days(raw: str) -> list[int]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [0, 1, 2, 3, 4]


def cron_matches_now(cron_expr: str, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    try:
        itr = croniter(cron_expr, now)
        prev = itr.get_prev(datetime)
        return (now - prev).total_seconds() < 60
    except Exception:
        return True
