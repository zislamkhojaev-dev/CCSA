import os

import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    os.environ.setdefault("APP_ENV", "development")
