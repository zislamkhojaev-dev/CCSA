"""Standardized API errors (Error Codes Matrix). Never leak internals to clients."""

from __future__ import annotations

from typing import Any

from fastapi import status


class ErrorCode:
    AUTH_UNAUTHORIZED = "AUTH_UNAUTHORIZED"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_FORBIDDEN = "AUTH_FORBIDDEN"
    AUTH_INACTIVE = "AUTH_INACTIVE"
    VAL_INVALID_INPUT = "VAL_INVALID_INPUT"
    VAL_NOT_FOUND = "VAL_NOT_FOUND"
    VAL_CONFLICT = "VAL_CONFLICT"
    DB_ERROR = "DB_ERROR"
    EXT_WEBITEL_UNAVAILABLE = "EXT_WEBITEL_UNAVAILABLE"
    EXT_LLM_UNAVAILABLE = "EXT_LLM_UNAVAILABLE"
    EXT_STT_UNAVAILABLE = "EXT_STT_UNAVAILABLE"
    EXT_STORAGE_UNAVAILABLE = "EXT_STORAGE_UNAVAILABLE"
    JOB_IN_PROGRESS = "JOB_IN_PROGRESS"
    JOB_NOT_READY = "JOB_NOT_READY"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    INTERNAL = "INTERNAL"


STATUS_TO_CODE = {
    400: ErrorCode.VAL_INVALID_INPUT,
    401: ErrorCode.AUTH_UNAUTHORIZED,
    403: ErrorCode.AUTH_FORBIDDEN,
    404: ErrorCode.VAL_NOT_FOUND,
    409: ErrorCode.VAL_CONFLICT,
    502: ErrorCode.EXT_WEBITEL_UNAVAILABLE,
    503: ErrorCode.EXT_STT_UNAVAILABLE,
    500: ErrorCode.INTERNAL,
}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}

    @classmethod
    def unauthorized(cls, message: str = "Требуется авторизация") -> AppError:
        return cls(ErrorCode.AUTH_UNAUTHORIZED, message, status.HTTP_401_UNAUTHORIZED)

    @classmethod
    def forbidden(cls, message: str = "Недостаточно прав") -> AppError:
        return cls(ErrorCode.AUTH_FORBIDDEN, message, status.HTTP_403_FORBIDDEN)

    @classmethod
    def not_found(cls, message: str = "Не найдено") -> AppError:
        return cls(ErrorCode.VAL_NOT_FOUND, message, status.HTTP_404_NOT_FOUND)

    @classmethod
    def invalid(cls, message: str) -> AppError:
        return cls(ErrorCode.VAL_INVALID_INPUT, message, status.HTTP_400_BAD_REQUEST)

    @classmethod
    def conflict(cls, message: str, code: str = ErrorCode.VAL_CONFLICT) -> AppError:
        return cls(code, message, status.HTTP_409_CONFLICT)

    @classmethod
    def feature_disabled(cls, name: str) -> AppError:
        return cls(
            ErrorCode.FEATURE_DISABLED,
            f"Функция «{name}» отключена",
            status.HTTP_403_FORBIDDEN,
        )


# User-facing pipeline messages — never store raw exception text on entities.
USER_ERROR_TRANSCRIBE = "Не удалось распознать речь. Повторите попытку."
USER_ERROR_ANALYZE = "Не удалось проанализировать звонок. Повторите попытку."
USER_ERROR_EXPORT = "Не удалось сформировать файл экспорта."
USER_ERROR_STORAGE = "Не удалось прочитать файл."
USER_ERROR_WEBITEL = "Webitel недоступен. Проверьте настройки коннектора."
USER_ERROR_GENERIC = "Внутренняя ошибка. Повторите попытку позже."
