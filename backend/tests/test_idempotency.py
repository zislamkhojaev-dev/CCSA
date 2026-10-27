from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError, ErrorCode
from app.services.idempotency import begin_idempotency, store_idempotency


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Scalars:
    def all(self):
        return []


class _Result:
    def scalars(self):
        return _Scalars()


class FakeSession:
    def __init__(self, *, existing=None, conflict: bool = False):
        self.existing = existing
        self._conflicts_left = 1 if conflict else 0
        self.added: list = []

    def begin_nested(self):
        return _Nested()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        if self._conflicts_left:
            self._conflicts_left -= 1
            raise IntegrityError("duplicate", "INSERT", {}, Exception("duplicate"))

    async def scalar(self, _stmt):
        if self.existing is not None:
            return self.existing
        return self.added[0] if self.added else None

    async def execute(self, _stmt):
        return _Result()

    async def delete(self, _obj):
        return None


def _row(**kwargs):
    base = dict(
        key="k1",
        user_id=1,
        request_hash="",
        state="completed",
        status_code=200,
        response_json={"ok": True},
        created_at=datetime.now(UTC),
        method="POST",
        path="/research",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


async def test_missing_key_does_not_touch_storage():
    session = FakeSession()
    record = await begin_idempotency(
        session, user_id=1, key=None, method="POST", path="/research", body={"a": 1}
    )
    assert record.replay is False
    assert session.added == []


async def test_key_longer_than_column_is_rejected():
    session = FakeSession()
    with pytest.raises(AppError) as exc:
        await begin_idempotency(
            session, user_id=1, key="x" * 129, method="POST", path="/research", body={}
        )
    assert exc.value.code == ErrorCode.VAL_INVALID_INPUT
    assert session.added == []


async def test_claim_is_inserted_before_the_response_is_stored():
    session = FakeSession()
    record = await begin_idempotency(
        session, user_id=7, key="k1", method="POST", path="/research", body={"title": "a"}
    )
    assert record.replay is False
    assert session.added[0].state == "pending"
    assert session.added[0].status_code == 0
    await store_idempotency(
        session,
        user_id=7,
        key="k1",
        method="POST",
        path="/research",
        body={"title": "a"},
        status_code=201,
        payload={"id": 4},
    )
    assert session.added[0].state == "completed"
    assert session.added[0].response_json == {"id": 4}
    assert len(session.added) == 1


async def test_completed_key_replays_and_does_not_repeat_the_effect():
    session = FakeSession()
    first = await begin_idempotency(
        session, user_id=7, key="k1", method="POST", path="/research", body={"title": "a"}
    )
    assert first.replay is False
    await store_idempotency(
        session,
        user_id=7,
        key="k1",
        method="POST",
        path="/research",
        body={"title": "a"},
        status_code=201,
        payload={"id": 4},
    )
    session._conflicts_left = 1
    session.existing = session.added[0]
    effects = 0
    second = await begin_idempotency(
        session, user_id=7, key="k1", method="POST", path="/research", body={"title": "a"}
    )
    if not second.replay:
        effects += 1
    assert second.replay is True
    assert second.payload == {"id": 4}
    assert effects == 0


async def test_same_key_with_other_body_conflicts():
    session = FakeSession(
        conflict=True,
        existing=_row(request_hash="different", state="completed"),
    )
    with pytest.raises(AppError) as exc:
        await begin_idempotency(
            session, user_id=1, key="k1", method="POST", path="/research", body={"title": "a"}
        )
    assert exc.value.code == ErrorCode.IDEMPOTENCY_CONFLICT


async def test_fresh_pending_key_is_in_progress():
    session = FakeSession(conflict=True, existing=_row(state="pending", status_code=0, response_json=None))
    # Match the hash of the request body so this is the same logical request.
    from app.services.idempotency import _request_hash

    session.existing.request_hash = _request_hash({"title": "a"})
    with pytest.raises(AppError) as exc:
        await begin_idempotency(
            session, user_id=1, key="k1", method="POST", path="/research", body={"title": "a"}
        )
    assert exc.value.code == ErrorCode.IDEMPOTENCY_IN_PROGRESS


async def test_stale_pending_key_can_be_reclaimed():
    from app.services.idempotency import _request_hash

    existing = _row(
        state="pending",
        status_code=0,
        response_json=None,
        created_at=datetime.now(UTC) - timedelta(seconds=500),
        request_hash=_request_hash({"title": "a"}),
    )
    session = FakeSession(conflict=True, existing=existing)
    record = await begin_idempotency(
        session, user_id=1, key="k1", method="POST", path="/research", body={"title": "a"}
    )
    assert record.replay is False
    assert existing.state == "pending"
    assert existing.created_at > datetime.now(UTC) - timedelta(seconds=5)
