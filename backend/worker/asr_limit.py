"""Limit concurrent STT HTTP requests (Redis tokens with TTL — no stuck counters)."""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager

import redis

logger = logging.getLogger(__name__)

_HOLDERS_ZSET = "ccsa:asr:holders"  # member=token, score=expires_at (unix)


def _redis() -> redis.Redis:
    return redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))


def _purge_expired(client: redis.Redis) -> int:
    now = time.time()
    removed = client.zremrangebyscore(_HOLDERS_ZSET, "-inf", now)
    return int(removed or 0)


def reset_asr_slots() -> None:
    """Clear all ASR concurrency tokens (e.g. after worker crash)."""
    client = _redis()
    client.delete(_HOLDERS_ZSET, "ccsa:asr:active_count")  # legacy counter key
    logger.info("ASR concurrency slots reset")


@contextmanager
def asr_concurrency_slot(max_parallel: int, *, acquire_timeout: float = 7200.0, slot_ttl: float = 900.0):
    """
    Block until a slot is free, then release after transcribe finishes.
    Tokens auto-expire after slot_ttl seconds if a worker dies without releasing.
    """
    limit = max(1, min(int(max_parallel), 8))
    client = _redis()
    token = uuid.uuid4().hex
    token_acquired = False
    deadline = time.monotonic() + acquire_timeout
    ttl = max(120.0, float(slot_ttl))

    try:
        while time.monotonic() < deadline:
            _purge_expired(client)
            active = client.zcard(_HOLDERS_ZSET)
            if active < limit:
                expires_at = time.time() + ttl
                pipe = client.pipeline()
                pipe.zadd(_HOLDERS_ZSET, {token: expires_at})
                pipe.zcard(_HOLDERS_ZSET)
                _, new_count = pipe.execute()
                if int(new_count) <= limit:
                    token_acquired = True
                    logger.debug("ASR slot acquired (%s/%s)", int(new_count), limit)
                    break
                client.zrem(_HOLDERS_ZSET, token)
            time.sleep(0.3)

        if not token_acquired:
            _purge_expired(client)
            stuck = client.zcard(_HOLDERS_ZSET)
            raise TimeoutError(
                f"Превышено время ожидания слота ASR ({int(acquire_timeout)} с). "
                f"Занято слотов: {stuck}/{limit}. "
                f"Перезапустите celery-worker или сбросьте очередь ASR."
            )
        yield
    finally:
        if token_acquired:
            try:
                client.zrem(_HOLDERS_ZSET, token)
            except Exception as e:
                logger.warning("Failed to release ASR slot %s: %s", token[:8], e)
