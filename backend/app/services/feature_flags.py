"""Feature toggles: env FEATURE_* overrides settings_store, then config defaults."""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import get_settings

FEATURE_KEYS = ("research", "playground", "webitel_sync", "dashboard_constructor")


def _env_override(name: str) -> bool | None:
    raw = os.getenv(f"FEATURE_{name.upper()}")
    if raw is None:
        return None
    return raw.lower() in ("1", "true", "yes", "on")


def _config_default(name: str) -> bool:
    settings = get_settings()
    return bool(getattr(settings, f"feature_{name}", True))


async def is_feature_enabled(db: AsyncSession, name: str) -> bool:
    env_val = _env_override(name)
    if env_val is not None:
        return env_val
    from app.services.settings_store import get_bool_setting

    return await get_bool_setting(db, f"feature_{name}", _config_default(name))


def is_feature_enabled_sync(db: Session, name: str) -> bool:
    env_val = _env_override(name)
    if env_val is not None:
        return env_val
    from worker.settings_sync import get_bool_setting_sync

    return get_bool_setting_sync(db, f"feature_{name}", _config_default(name))


async def require_feature(db: AsyncSession, name: str) -> None:
    from app.core.errors import AppError

    if not await is_feature_enabled(db, name):
        raise AppError.feature_disabled(name)
