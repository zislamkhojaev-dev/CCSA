from contextlib import contextmanager

from app.database import SyncSessionLocal


@contextmanager
def get_sync_session():
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
