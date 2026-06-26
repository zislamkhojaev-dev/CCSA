import json
import os
from typing import Any

import redis

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    return _redis


def publish_playground_event(job_id: int, payload: dict[str, Any]) -> None:
    channel = f"playground:job:{job_id}"
    get_redis().publish(channel, json.dumps(payload))


def publish_research_event(study_id: int, payload: dict[str, Any]) -> None:
    channel = f"research:study:{study_id}"
    get_redis().publish(channel, json.dumps(payload))


def subscribe_playground_events(job_id: int):
    r = get_redis()
    pubsub = r.pubsub()
    pubsub.subscribe(f"playground:job:{job_id}")
    return pubsub


def subscribe_research_events(study_id: int):
    r = get_redis()
    pubsub = r.pubsub()
    pubsub.subscribe(f"research:study:{study_id}")
    return pubsub
