"""Per-call task locks in Redis.

The DB `calls.status` field is user-visible state, not a concurrency primitive:
a worker killed mid-run leaves it at `analyzing`/`transcribing` forever, and any
retry then refuses to start. Locks live in Redis with a TTL instead, so a dead
worker releases its claim automatically.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager

from app.config import get_settings
from app.core.logging import log_error
from app.services.redis_client import get_redis

logger = logging.getLogger(__name__)


def _lock_ttl() -> int:
    return get_settings().redis_lock_ttl_sec


def _key(kind: str, call_id: int) -> str:
    return f"ccsa:lock:{kind}:{call_id}"


def is_locked(kind: str, call_id: int) -> bool:
    try:
        return bool(get_redis().exists(_key(kind, call_id)))
    except Exception as e:
        log_error(logger, "Lock check failed", method="is_locked", params={"kind": kind, "call_id": call_id}, exc=e)
        return False


def release(kind: str, call_id: int) -> None:
    try:
        get_redis().delete(_key(kind, call_id))
    except Exception as e:
        log_error(logger, "Lock release failed", method="release", params={"kind": kind, "call_id": call_id}, exc=e)


@contextmanager
def call_task_lock(kind: str, call_id: int, *, ttl: int | None = None):
    """Yield True when the lock was claimed, False when another worker holds it.

    If Redis is unreachable the work is allowed to proceed unlocked — losing
    deduplication is preferable to blocking the pipeline entirely.
    """
    key = _key(kind, call_id)
    token = uuid.uuid4().hex
    acquired = False
    client = None
    lock_ttl = ttl if ttl is not None else _lock_ttl()

    try:
        client = get_redis()
        acquired = bool(client.set(key, token, nx=True, ex=max(60, int(lock_ttl))))
    except Exception as e:
        log_error(logger, "Lock acquire failed, proceeding unlocked", method="call_task_lock", params={"key": key}, exc=e)
        yield True
        return

    try:
        yield acquired
    finally:
        if acquired and client is not None:
            try:
                if client.get(key) == token:
                    client.delete(key)
            except Exception as e:
                log_error(logger, "Lock release failed", method="call_task_lock", params={"key": key}, exc=e)
