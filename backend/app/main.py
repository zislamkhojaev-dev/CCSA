from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import api_router
from app.config import get_settings
from app.core.context import get_trace_id, reset_context, set_method, set_trace_id
from app.core.errors import STATUS_TO_CODE, AppError, ErrorCode, USER_ERROR_GENERIC
from app.core.logging import log_error, setup_logging
import logging

logger = logging.getLogger(__name__)


def _error_body(code: str, message: str) -> dict:
    return {"error_code": code, "message": message, "trace_id": get_trace_id() or None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level=get_settings().log_level)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CCSA Speech Analytics", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        reset_context()
        trace_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_trace_id(trace_id)
        set_method(f"{request.method} {request.url.path}")
        try:
            response = await call_next(request)
        finally:
            pass
        response.headers["X-Request-ID"] = trace_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        log_error(
            logger,
            exc.message,
            method=f"{request.method} {request.url.path}",
            params={"error_code": exc.code, "path": request.url.path},
        )
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message))

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else USER_ERROR_GENERIC
        code = STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL)
        return JSONResponse(status_code=exc.status_code, content=_error_body(code, message))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_error_body(ErrorCode.VAL_INVALID_INPUT, "Некорректные данные запроса"),
        )

    @app.exception_handler(SQLAlchemyError)
    async def db_error_handler(request: Request, exc: SQLAlchemyError):
        log_error(logger, "Database error", method=f"{request.method} {request.url.path}", exc=exc)
        return JSONResponse(status_code=500, content=_error_body(ErrorCode.DB_ERROR, USER_ERROR_GENERIC))

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        log_error(logger, "Unhandled error", method=f"{request.method} {request.url.path}", exc=exc)
        return JSONResponse(status_code=500, content=_error_body(ErrorCode.INTERNAL, USER_ERROR_GENERIC))

    app.include_router(api_router)
    return app


app = create_app()
