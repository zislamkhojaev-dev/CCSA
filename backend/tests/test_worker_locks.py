import pytest

from worker.task_lock import is_locked


def test_is_locked_false_when_redis_down(monkeypatch):
    monkeypatch.setattr("worker.task_lock.get_redis", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert is_locked("analyze", 1) is False


def test_stt_client_raises_http_error(monkeypatch):
    import httpx
    from app.services.stt_client import SttClient

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError("stt down")

    monkeypatch.setattr("app.services.stt_client.httpx.Client", FakeClient)
    with pytest.raises(httpx.ConnectError):
        SttClient().transcribe("key", timeout_sec=1)
