"""Exponential backoff with jitter for third-party calls."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def backoff_seconds(attempt: int, *, base: float = 0.5, cap: float = 8.0) -> float:
    return min(cap, base * (2**attempt)) + random.uniform(0, 0.25)


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int,
    exceptions: tuple[type[BaseException], ...],
    method: str = "retry_async",
) -> T:
    last: BaseException | None = None
    attempts = max(1, retries)
    for attempt in range(attempts):
        try:
            return await fn()
        except exceptions as exc:
            last = exc
            if attempt >= attempts - 1:
                break
            delay = backoff_seconds(attempt)
            logger.warning(
                "%s attempt %s/%s failed, retry in %.2fs: %s",
                method,
                attempt + 1,
                attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    assert last is not None
    raise last


def retry_sync(
    fn: Callable[[], T],
    *,
    retries: int,
    exceptions: tuple[type[BaseException], ...],
    method: str = "retry_sync",
) -> T:
    last: BaseException | None = None
    attempts = max(1, retries)
    for attempt in range(attempts):
        try:
            return fn()
        except exceptions as exc:
            last = exc
            if attempt >= attempts - 1:
                break
            delay = backoff_seconds(attempt)
            logger.warning(
                "%s attempt %s/%s failed, retry in %.2fs: %s",
                method,
                attempt + 1,
                attempts,
                delay,
                exc,
            )
            time.sleep(delay)
    assert last is not None
    raise last
