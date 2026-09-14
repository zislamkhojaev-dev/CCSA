from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models import IdempotencyKey


@dataclass
class IdempotencyRecord:
    key: str | None
    replay: bool = False
    status_code: int = 200
    payload: Any = None


async def begin_idempotency(
    db: AsyncSession,
    *,
    user_id: int,
    key: str | None,
    method: str,
    path: str,
    body: Any,
) -> IdempotencyRecord:
    if not key:
        return IdempotencyRecord(key=None)
    request_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    existing = await db.scalar(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
    )
    if existing:
        if existing.request_hash != request_hash:
            raise AppError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "Idempotency-Key уже использован с другим телом запроса",
                409,
            )
        return IdempotencyRecord(
            key=key,
            replay=True,
            status_code=existing.status_code,
            payload=existing.response_json,
        )
    return IdempotencyRecord(key=key)


async def store_idempotency(
    db: AsyncSession,
    *,
    user_id: int,
    key: str,
    method: str,
    path: str,
    body: Any,
    status_code: int,
    payload: Any,
) -> None:
    request_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    db.add(
        IdempotencyKey(
            key=key,
            user_id=user_id,
            method=method,
            path=path,
            request_hash=request_hash,
            status_code=status_code,
            response_json=payload,
        )
    )
    await _purge_expired(db)


async def _purge_expired(db: AsyncSession) -> None:
    ttl = get_settings().idempotency_ttl_hours
    cutoff = datetime.now(UTC) - timedelta(hours=ttl)
    rows = await db.execute(select(IdempotencyKey).where(IdempotencyKey.created_at < cutoff))
    for row in rows.scalars().all():
        await db.delete(row)


def idempotency_key_header(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str | None:
    return idempotency_key


async def request_body_json(request: Request) -> Any:
    if request.method in ("GET", "HEAD"):
        return {}
    try:
        return await request.json()
    except Exception:
        return {}
