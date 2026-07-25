"""Extract operators from Webitel call history.

Shared by the API endpoint (runs synchronously so the UI can report what changed)
and the Celery task. Only the parsing lives here; each caller persists with its
own session flavour (async in the API, sync in the worker).
"""

from __future__ import annotations

from datetime import datetime, timedelta

OPERATOR_LOOKBACK_DAYS = 7


def operator_lookback_start() -> datetime:
    return datetime.utcnow() - timedelta(days=OPERATOR_LOOKBACK_DAYS)


def extract_operators(items: list[dict]) -> list[tuple[str, str]]:
    """Return unique (webitel_id, full_name) pairs in first-seen order."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in items:
        webitel_id = str(item.get("agent_id") or item.get("user_id") or "").strip()
        name = (item.get("agent_name") or item.get("user_name") or "").strip()
        if not webitel_id or not name or webitel_id in seen:
            continue
        seen.add(webitel_id)
        pairs.append((webitel_id, name))
    return pairs
