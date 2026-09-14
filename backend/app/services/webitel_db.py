import logging

import psycopg2

from app.config import get_settings
from app.core.logging import log_error

logger = logging.getLogger(__name__)


def _connect(host: str, port: int, database: str, user: str, password: str):
    timeout = get_settings().webitel_db_connect_timeout
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
        connect_timeout=timeout,
        options=f"-c statement_timeout={get_settings().db_statement_timeout_ms}",
    )


def test_connection(host: str, port: int, database: str, user: str, password: str) -> tuple[bool, str]:
    try:
        conn = _connect(host, port, database, user, password)
        conn.close()
        return True, "Соединение установлено"
    except Exception as e:
        log_error(logger, "Webitel DB test failed", method="test_connection", exc=e)
        return False, "Не удалось подключиться к базе Webitel"


def fetch_recent_calls(
    host: str, port: int, database: str, user: str, password: str, limit: int = 50
) -> list[dict]:
    """
    Optional read-only sync from Webitel PostgreSQL.
    Uses generic query — adjust table names to your Webitel schema if needed.
    """
    try:
        conn = _connect(host, port, database, user, password)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id::text, created_at, duration
            FROM calls
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"id": r[0], "created_at": r[1], "duration": r[2]} for r in rows]
    except Exception as e:
        log_error(logger, "Webitel DB fetch failed", method="fetch_recent_calls", exc=e)
        return []


class WebitelDbAdapter:
    def test_connection(self, host: str, port: int, database: str, user: str, password: str) -> tuple[bool, str]:
        return test_connection(host, port, database, user, password)

    def fetch_recent_calls(
        self, host: str, port: int, database: str, user: str, password: str, limit: int = 50
    ) -> list[dict]:
        return fetch_recent_calls(host, port, database, user, password, limit)


webitel_db_adapter = WebitelDbAdapter()
