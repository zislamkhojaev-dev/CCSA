from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.errors import AppError, ErrorCode
from app.services.call_service import parse_date
from app.services.feature_flags import _env_override
from app.services.operator_service import OperatorService


def test_parse_date_end_of_day():
    dt = parse_date("2026-01-02", end_of_day=True)
    assert dt is not None
    assert dt.hour == 23
    assert dt.minute == 59


def test_parse_date_invalid():
    assert parse_date("not-a-date") is None


def test_feature_env_override(monkeypatch):
    monkeypatch.setenv("FEATURE_RESEARCH", "false")
    assert _env_override("research") is False
    monkeypatch.setenv("FEATURE_RESEARCH", "true")
    assert _env_override("research") is True


@pytest.mark.asyncio
async def test_operator_sync_requires_url(monkeypatch):
    async def fake_get_setting(_db, _key, default=""):
        return default

    monkeypatch.setattr("app.services.operator_service.get_setting", fake_get_setting)
    svc = OperatorService()
    with pytest.raises(AppError) as exc:
        await svc.sync_operators(AsyncMock())
    assert exc.value.code == ErrorCode.VAL_INVALID_INPUT


@pytest.mark.asyncio
async def test_webitel_retry_exhausted():
    from app.core.retry import retry_async

    async def boom():
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        await retry_async(boom, retries=2, exceptions=(httpx.HTTPError,), method="test")


@pytest.mark.asyncio
async def test_operator_sync_persists_new(monkeypatch):
    async def fake_get_setting(_db, key, default=""):
        if key == "webitel_api_url":
            return "https://webitel.example"
        return "token"

    monkeypatch.setattr("app.services.operator_service.get_setting", fake_get_setting)
    webitel = MagicMock()
    webitel.fetch_call_history = AsyncMock(return_value=[{"agent_id": "1", "agent_name": "Ali"}])
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.flush = AsyncMock()
    svc = OperatorService()
    out = await svc.sync_operators(db, webitel=webitel)
    assert out.created == 1
    assert out.found == 1
    db.add.assert_called()
