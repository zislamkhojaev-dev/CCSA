from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_value
from app.models import AppSetting

DEFAULTS = {
    "pii_anonymization": "true",
    "openai_api_key": "",
    "llm_model": "gpt-4o-mini",
}


def get_setting_sync(db: Session, key: str, default: str = "") -> str:
    row = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
    if not row:
        return DEFAULTS.get(key, default)
    try:
        return decrypt_value(row.value_encrypted)
    except Exception:
        return default


def get_bool_setting_sync(db: Session, key: str, default: bool = False) -> bool:
    val = get_setting_sync(db, key, "true" if default else "false")
    return val.lower() in ("1", "true", "yes", "on")
