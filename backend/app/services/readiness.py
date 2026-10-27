"""Dependency checks for GET /ready. Probe responses never include exception text or DSNs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import redis
import urllib3
from minio import Minio
from sqlalchemy import text

from app.config import get_settings
from app.core.logging import log_error
from app.database import async_engine

logger = logging.getLogger(__name__)

Check = Callable[[], Awaitable[bool]]


async def _check_database() -> bool:
    async with async_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True


async def _check_redis() -> bool:
    settings = get_settings()
    timeout = settings.readiness_timeout_sec

    def ping() -> bool:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
        )
        try:
            return bool(client.ping())
        finally:
            client.close()

    return await asyncio.to_thread(ping)


async def _check_storage() -> bool:
    settings = get_settings()
    timeout = settings.readiness_timeout_sec

    def bucket_ok() -> bool:
        http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=timeout, read=timeout))
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            http_client=http,
        )
        return bool(client.bucket_exists(settings.minio_bucket))

    return await asyncio.to_thread(bucket_ok)


async def collect_readiness(
    *,
    check_database: Check | None = None,
    check_redis: Check | None = None,
    check_storage: Check | None = None,
) -> tuple[bool, dict[str, str]]:
    timeout = get_settings().readiness_timeout_sec
    spec: dict[str, Check] = {
        "database": check_database or _check_database,
        "redis": check_redis or _check_redis,
        "storage": check_storage or _check_storage,
    }
    async def run(name: str, fn: Check) -> tuple[str, str]:
        try:
            ok = await asyncio.wait_for(fn(), timeout=timeout)
            return name, "ok" if ok else "error"
        except Exception as exc:
            log_error(
                logger,
                "Readiness check failed",
                method="collect_readiness",
                params={"check": name},
                exc=exc,
            )
            return name, "error"

    results = await asyncio.gather(*(run(name, fn) for name, fn in spec.items()))
    checks = dict(results)
    return all(value == "ok" for value in checks.values()), checks
