"""Configurable quality thresholds and call-topic taxonomy for the dashboard.

Shared by dashboard metrics (colors, buckets, target line) and the LLM
classification step (allowed topics).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_store import get_setting

# Score buckets (percent). Green >= good, Yellow >= mid, else Red.
DEFAULT_THRESHOLD_GOOD = 80
DEFAULT_THRESHOLD_MID = 50
DEFAULT_TARGET = 85

# Label used for calls with no assigned topic.
UNCLASSIFIED_TOPIC = "Не классифицировано"

DEFAULT_TAXONOMY: list[str] = [
    "Оформление заказа",
    "Консультация",
    "Статус заказа",
    "Жалоба",
    "Возврат / обмен",
    "Техническая поддержка",
    "Спам / ошибочный",
]


@dataclass(frozen=True)
class QualityConfig:
    threshold_good: int = DEFAULT_THRESHOLD_GOOD
    threshold_mid: int = DEFAULT_THRESHOLD_MID
    target: int = DEFAULT_TARGET
    topics: list[str] = field(default_factory=lambda: list(DEFAULT_TAXONOMY))

    def bucket(self, score: float | None) -> str:
        """Return 'green' | 'yellow' | 'red' | 'gray' for a score."""
        if score is None:
            return "gray"
        if score >= self.threshold_good:
            return "green"
        if score >= self.threshold_mid:
            return "yellow"
        return "red"


def _parse_int(raw: str, default: int, *, min_val: int = 0, max_val: int = 100) -> int:
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = default
    return max(min_val, min(max_val, value))


def parse_topics(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return list(DEFAULT_TAXONOMY)
    if not isinstance(data, list):
        return list(DEFAULT_TAXONOMY)
    seen: set[str] = set()
    result: list[str] = []
    for item in data:
        name = str(item).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            result.append(name)
    return result or list(DEFAULT_TAXONOMY)


def normalize_config(
    *, threshold_good: int, threshold_mid: int, target: int, topics: list[str]
) -> QualityConfig:
    good = max(0, min(100, threshold_good))
    mid = max(0, min(good, threshold_mid))  # mid can't exceed good
    tgt = max(0, min(100, target))
    clean_topics: list[str] = []
    seen: set[str] = set()
    for t in topics:
        name = str(t).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            clean_topics.append(name)
    return QualityConfig(
        threshold_good=good,
        threshold_mid=mid,
        target=tgt,
        topics=clean_topics or list(DEFAULT_TAXONOMY),
    )


async def load_quality_config(db: AsyncSession) -> QualityConfig:
    good = _parse_int(await get_setting(db, "quality_threshold_good", str(DEFAULT_THRESHOLD_GOOD)), DEFAULT_THRESHOLD_GOOD)
    mid = _parse_int(await get_setting(db, "quality_threshold_mid", str(DEFAULT_THRESHOLD_MID)), DEFAULT_THRESHOLD_MID)
    target = _parse_int(await get_setting(db, "quality_target", str(DEFAULT_TARGET)), DEFAULT_TARGET)
    topics = parse_topics(await get_setting(db, "call_topics", json.dumps(DEFAULT_TAXONOMY, ensure_ascii=False)))
    if mid > good:
        mid = good
    return QualityConfig(threshold_good=good, threshold_mid=mid, target=target, topics=topics)
