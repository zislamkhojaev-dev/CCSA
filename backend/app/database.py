from collections.abc import AsyncGenerator
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings
from app.core.logging import log_error

logger = logging.getLogger(__name__)

settings = get_settings()


def with_psycopg2_driver(url: str) -> str:
    """SQLAlchemy 2.1 reads a bare postgresql:// URL as psycopg 3."""
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url.removeprefix("postgres://")
    return url


async_engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_timeout=settings.db_pool_timeout,
    connect_args={
        "timeout": settings.db_connect_timeout,
        "server_settings": {"statement_timeout": str(settings.db_statement_timeout_ms)},
    },
)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

sync_engine = create_engine(
    with_psycopg2_driver(settings.database_url_sync),
    pool_pre_ping=True,
    pool_timeout=settings.db_pool_timeout,
    connect_args={
        "connect_timeout": settings.db_connect_timeout,
        "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
    },
)
SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)


@event.listens_for(sync_engine, "connect")
def _set_sync_statement_timeout(dbapi_connection, _connection_record) -> None:
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET statement_timeout = {int(settings.db_statement_timeout_ms)}")
        cursor.close()
    except Exception:
        logger.warning("Could not set statement_timeout on sync connection")


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            log_error(logger, "Database session rolled back", method="get_db")
            raise
