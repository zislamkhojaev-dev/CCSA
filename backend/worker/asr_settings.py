"""Read ASR performance settings from app_settings (sync, for Celery worker)."""

from sqlalchemy.orm import Session

from worker.settings_sync import get_bool_setting_sync, get_setting_sync


def get_int_setting_sync(db: Session, key: str, default: int, *, min_val: int = 1, max_val: int = 86400) -> int:
    raw = get_setting_sync(db, key, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(min_val, min(max_val, value))


def asr_max_parallel(db: Session) -> int:
    return get_int_setting_sync(db, "asr_max_parallel", 1, min_val=1, max_val=8)


def asr_http_timeout_sec(db: Session) -> float:
    return float(get_int_setting_sync(db, "asr_http_timeout_sec", 600, min_val=60, max_val=7200))


def playground_sequential(db: Session) -> bool:
    return get_bool_setting_sync(db, "playground_sequential", True)
