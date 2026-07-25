"""Per-call task locks in Redis.

The DB `calls.status` field is user-visible state, not a concurrency primitive:
a worker killed mid-run leaves it at `analyzing`/`transcribing` forever, and any
retry then refuses to start. Locks live in Redis with a TTL instead, so a dead
worker releases its claim automatically.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import contextmanager

import redis

logger = logging.getLogger(__name__)

DEFAULT_LOCK_TTL = 1800


def _redis() -> redis.Redis:
    return redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))


def _key(kind: str, call_id: int) -> str:
    return f"ccsa:lock:{kind}:{call_id}"


def is_locked(kind: str, call_id: int) -> bool:
    try:
        return bool(_redis().exists(_key(kind, call_id)))
    except Exception as e:
        logger.warning("Lock check failed for %s:%s: %s", kind, call_id, e)
        return False


def release(kind: str, call_id: int) -> None:
    try:
        _redis().delete(_key(kind, call_id))
    except Exception as e:
        logger.warning("Lock release failed for %s:%s: %s", kind, call_id, e)


@contextmanager
def call_task_lock(kind: str, call_id: int, *, ttl: int = DEFAULT_LOCK_TTL):
    """Yield True when the lock was claimed, False when another worker holds it.

    If Redis is unreachable the work is allowed to proceed unlocked — losing
    deduplication is preferable to blocking the pipeline entirely.
    """
    key = _key(kind, call_id)
    token = uuid.uuid4().hex
    acquired = False
    client: redis.Redis | None = None

    try:
        client = _redis()
        acquired = bool(client.set(key, token, nx=True, ex=max(60, int(ttl))))
    except Exception as e:
        logger.warning("Lock acquire failed for %s, proceeding unlocked: %s", key, e)
        yield True
        return

    try:
        yield acquired
    finally:
        if acquired and client is not None:
            try:
                if client.get(key) == token.encode():
                    client.delete(key)
            except Exception as e:
                logger.warning("Lock release failed for %s: %s", key, e)
