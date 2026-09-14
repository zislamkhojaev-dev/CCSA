"""Request-scoped context for structured logs (trace_id, user_id)."""

from __future__ import annotations

from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_user_id: ContextVar[int | None] = ContextVar("user_id", default=None)
_method: ContextVar[str] = ContextVar("method", default="")


def get_trace_id() -> str:
    return _trace_id.get() or ""


def set_trace_id(value: str) -> None:
    _trace_id.set(value)


def get_user_id() -> int | None:
    return _user_id.get()


def set_user_id(value: int | None) -> None:
    _user_id.set(value)


def get_method() -> str:
    return _method.get() or ""


def set_method(value: str) -> None:
    _method.set(value)


def reset_context() -> None:
    _trace_id.set("")
    _user_id.set(None)
    _method.set("")
