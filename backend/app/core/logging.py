"""JSON structured logging with trace_id / user_id and secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.context import get_method, get_trace_id, get_user_id

_REDACT_KEYS = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|access_token|refresh_token|cookie)",
    re.IGNORECASE,
)
_REDACT_INLINE = re.compile(
    r"(password|token|api[_-]?key|secret|authorization)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "***" if _REDACT_KEYS.search(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _REDACT_INLINE.sub(lambda m: m.group(1) + "=***", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "method": getattr(record, "method", None) or get_method() or record.funcName,
            "trace_id": getattr(record, "trace_id", None) or get_trace_id() or None,
            "user_id": getattr(record, "user_id", None) or get_user_id(),
        }
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        extra_params = getattr(record, "params", None)
        if extra_params is not None:
            payload["params"] = redact(extra_params)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(*, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def log_error(
    logger: logging.Logger,
    message: str,
    *,
    method: str | None = None,
    params: dict[str, Any] | None = None,
    exc: BaseException | None = None,
) -> None:
    extra: dict[str, Any] = {}
    if method:
        extra["method"] = method
    if params is not None:
        extra["params"] = params
    if exc is not None:
        logger.error(message, extra=extra, exc_info=exc)
    else:
        logger.error(message, extra=extra)
