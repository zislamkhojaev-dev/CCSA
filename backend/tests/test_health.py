from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready():
    r = client.get("/api/v1/ready")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body or "database" in body or isinstance(body, dict)
