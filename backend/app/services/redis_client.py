"""Shared Redis client (EventBus + locks + ASR limiter)."""

from __future__ import annotations

from typing import Any

import redis

from app.config import get_settings

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


class RedisEventBus:
    def publish(self, channel: str, payload: dict[str, Any]) -> None:
        import json

        get_redis().publish(channel, json.dumps(payload))

    def subscribe(self, channel: str):
        pubsub = get_redis().pubsub()
        pubsub.subscribe(channel)
        return pubsub


event_bus = RedisEventBus()
