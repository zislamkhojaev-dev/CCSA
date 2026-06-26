import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_value, encrypt_value
from app.models import AppSetting

DEFAULT_SETTINGS = {
    "asr_provider": "local",
    "asr_model": "OvozifyLabs/whisper-small-uz-v1",
    "asr_diarization_method": "stereo_channels",
    "llm_provider": "openai",
    "llm_model": "gpt-4o-mini",
    "pii_anonymization": "true",
    "webitel_api_url": "",
    "webitel_access_token": "",
    "webitel_sync_cron": "*/30 * * * *",
    "webitel_sync_days": json.dumps([0, 1, 2, 3, 4]),
    "webitel_sync_time_from": "09:00",
    "webitel_sync_time_to": "18:00",
    "asr_max_parallel": "1",
    "asr_http_timeout_sec": "600",
    "playground_sequential": "true",
    "celery_worker_concurrency": "1",
}


async def get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    if not row:
        return DEFAULT_SETTINGS.get(key, default)
    try:
        return decrypt_value(row.value_encrypted)
    except Exception:
        return default


async def set_setting(db: AsyncSession, key: str, value: str) -> None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    encrypted = encrypt_value(value)
    if row:
        row.value_encrypted = encrypted
    else:
        db.add(AppSetting(key=key, value_encrypted=encrypted))


async def get_bool_setting(db: AsyncSession, key: str, default: bool = False) -> bool:
    val = await get_setting(db, key, "true" if default else "false")
    return val.lower() in ("1", "true", "yes", "on")
