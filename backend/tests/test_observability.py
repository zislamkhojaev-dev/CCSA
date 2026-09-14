from pydantic import ValidationError
import pytest

from app.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import redact
from app.core.retry import backoff_seconds


def test_health_error_envelope():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.headers.get("X-Request-ID")


def test_app_error_codes():
    err = AppError.not_found("missing")
    assert err.code == ErrorCode.VAL_NOT_FOUND
    assert err.status_code == 404


def test_redact_secrets():
    payload = redact({"password": "secret", "login": "admin", "token": "abc"})
    assert payload["password"] == "***"
    assert payload["token"] == "***"
    assert payload["login"] == "admin"


def test_backoff_grows():
    first = backoff_seconds(0, base=1, cap=20)
    third = backoff_seconds(3, base=1, cap=20)
    assert 1 <= first < 2.5
    assert third > first


def test_production_rejects_dev_defaults(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")


def test_development_allows_defaults():
    s = Settings(_env_file=None, app_env="development")
    assert s.cookie_secure is False
    assert s.cors_origin_list == ["*"]
