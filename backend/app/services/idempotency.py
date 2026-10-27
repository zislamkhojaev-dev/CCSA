from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Header, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models import IdempotencyKey

_PENDING = "pending"
_COMPLETED = "completed"


@dataclass
class IdempotencyRecord:
    key: str | None
    replay: bool = False
    status_code: int = 200
    payload: Any = None


def _request_hash(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def begin_idempotency(
    db: AsyncSession,
    *,
    user_id: int,
    key: str | None,
    method: str,
    path: str,
    body: Any,
) -> IdempotencyRecord:
    """Claim the key before the side effect.

    The insert participates in the request transaction. A concurrent request
    blocks on the unique (user_id, key) constraint until this transaction
    commits, then either replays the stored response or receives 409.
    """
    if not key:
        return IdempotencyRecord(key=None)
    if len(key) > 128:
        raise AppError.invalid("Idempotency-Key длиннее 128 символов")
    request_hash = _request_hash(body)
    claim = IdempotencyKey(
        key=key,
        user_id=user_id,
        method=method,
        path=path[:255],
        request_hash=request_hash,
        status_code=0,
        response_json=None,
        state=_PENDING,
    )
    try:
        async with db.begin_nested():
            db.add(claim)
            await db.flush()
    except IntegrityError:
        existing = await _existing(db, user_id, key)
        if existing is None:
            raise AppError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "Не удалось занять Idempotency-Key. Повторите запрос.",
                409,
            ) from None
        return await _resolve_existing(db, existing, request_hash=request_hash, method=method, path=path)
    return IdempotencyRecord(key=key)


async def _resolve_existing(
    db: AsyncSession,
    existing: IdempotencyKey,
    *,
    request_hash: str,
    method: str,
    path: str,
) -> IdempotencyRecord:
    if existing.request_hash != request_hash:
        raise AppError(
            ErrorCode.IDEMPOTENCY_CONFLICT,
            "Idempotency-Key уже использован с другим телом запроса",
            409,
        )
    if existing.state == _COMPLETED:
        return IdempotencyRecord(
            key=existing.key,
            replay=True,
            status_code=existing.status_code,
            payload=existing.response_json,
        )
    created_at = existing.created_at or datetime.now(UTC)
    pending_for = datetime.now(UTC) - _aware(created_at)
    if pending_for >= timedelta(seconds=get_settings().idempotency_pending_seconds):
        existing.method = method
        existing.path = path[:255]
        existing.status_code = 0
        existing.response_json = None
        existing.state = _PENDING
        existing.created_at = datetime.now(UTC)
        await db.flush()
        return IdempotencyRecord(key=existing.key)
    raise AppError(
        ErrorCode.IDEMPOTENCY_IN_PROGRESS,
        "Запрос с этим Idempotency-Key ещё выполняется. Повторите позже.",
        409,
    )


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
    request_hash = _request_hash(body)
    row = await _existing(db, user_id, key)
    if row is None:
        db.add(
            IdempotencyKey(
                key=key,
                user_id=user_id,
                method=method,
                path=path[:255],
                request_hash=request_hash,
                status_code=status_code,
                response_json=payload,
                state=_COMPLETED,
            )
        )
    else:
        row.method = method
        row.path = path[:255]
        row.request_hash = request_hash
        row.status_code = status_code
        row.response_json = payload
        row.state = _COMPLETED
    await _purge_expired(db)


async def _existing(db: AsyncSession, user_id: int, key: str) -> IdempotencyKey | None:
    return await db.scalar(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
    )


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
