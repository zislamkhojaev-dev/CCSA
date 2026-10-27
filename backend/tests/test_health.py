from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready(monkeypatch):
    async def fake():
        return True, {"database": "ok", "redis": "ok", "storage": "ok"}

    monkeypatch.setattr("app.api.health.collect_readiness", fake)
    r = client.get("/api/v1/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert r.json()["checks"]["database"] == "ok"


def test_ready_is_not_ready_when_a_dependency_fails(monkeypatch):
    async def fake():
        return False, {"database": "error", "redis": "ok", "storage": "ok"}

    monkeypatch.setattr("app.api.health.collect_readiness", fake)
    r = client.get("/api/v1/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert "password" not in str(body)
    assert "ccsa_secret" not in str(body)


async def test_collect_readiness_fails_closed_without_leaking_the_error():
    from app.services.readiness import collect_readiness

    async def down():
        raise RuntimeError("postgresql://ccsa:ccsa_secret@postgres/ccsa")

    async def up():
        return True

    ok, checks = await collect_readiness(check_database=down, check_redis=up, check_storage=up)
    assert ok is False
    assert checks == {"database": "error", "redis": "ok", "storage": "ok"}
    assert "ccsa_secret" not in str(checks)
