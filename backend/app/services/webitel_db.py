import logging

import psycopg2

logger = logging.getLogger(__name__)


def test_connection(host: str, port: int, database: str, user: str, password: str) -> tuple[bool, str]:
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=password,
            connect_timeout=10,
        )
        conn.close()
        return True, "Соединение установлено"
    except Exception as e:
        logger.warning("Webitel DB test failed: %s", e)
        return False, str(e)


def fetch_recent_calls(host: str, port: int, database: str, user: str, password: str, limit: int = 50) -> list[dict]:
    """
    Optional read-only sync from Webitel PostgreSQL.
    Uses generic query — adjust table names to your Webitel schema if needed.
    """
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=database, user=user, password=password)
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
        logger.warning("Webitel DB fetch failed (schema may differ): %s", e)
        return []
