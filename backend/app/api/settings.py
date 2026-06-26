import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_admin_user, get_current_user
from app.database import get_db
from app.core.security import hash_password
from app.models import AutomationRule, User
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.common import MessageOut
from app.schemas.settings import (
    AutomationRuleOut,
    AutomationRuleUpdate,
    SettingsModelsOut,
    SettingsUpdate,
    WebitelDbSettings,
    WebitelSettings,
)
from app.services.settings_store import get_bool_setting, get_setting, set_setting


def _parse_int_setting(raw: str, default: int, *, min_val: int, max_val: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(min_val, min(max_val, value))
from app.services.webitel import WebitelClient
from app.services.webitel_db import test_connection as test_webitel_db

router = APIRouter()


@router.get("/models", response_model=SettingsModelsOut)
async def get_models_settings(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    openai_key = await get_setting(db, "openai_api_key")
    asr_key = await get_setting(db, "asr_api_key")
    return SettingsModelsOut(
        asr_provider=await get_setting(db, "asr_provider", "local"),
        asr_model=await get_setting(db, "asr_model", "OvozifyLabs/whisper-small-uz-v1"),
        asr_diarization_method=await get_setting(db, "asr_diarization_method", "stereo_channels"),
        asr_api_url=await get_setting(db, "asr_api_url", ""),
        asr_api_key_set=bool(asr_key),
        llm_provider=await get_setting(db, "llm_provider", "openai"),
        llm_model=await get_setting(db, "llm_model", "gpt-4o-mini"),
        pii_anonymization=await get_bool_setting(db, "pii_anonymization", True),
        openai_api_key_set=bool(openai_key),
        gemini_api_key_set=bool(await get_setting(db, "gemini_api_key")),
        ollama_base_url=await get_setting(db, "ollama_base_url", "http://host.docker.internal:11434"),
        asr_max_parallel=_parse_int_setting(
            await get_setting(db, "asr_max_parallel", "1"), 1, min_val=1, max_val=8
        ),
        asr_http_timeout_sec=_parse_int_setting(
            await get_setting(db, "asr_http_timeout_sec", "600"), 600, min_val=60, max_val=7200
        ),
        playground_sequential=await get_bool_setting(db, "playground_sequential", True),
        celery_worker_concurrency=_parse_int_setting(
            await get_setting(db, "celery_worker_concurrency", "1"), 1, min_val=1, max_val=8
        ),
    )


@router.put("/models", response_model=MessageOut)
async def update_models_settings(
    body: SettingsUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)
):
    if body.asr_provider is not None:
        await set_setting(db, "asr_provider", body.asr_provider)
    if body.asr_model is not None:
        await set_setting(db, "asr_model", body.asr_model)
    if body.asr_diarization_method is not None:
        await set_setting(db, "asr_diarization_method", body.asr_diarization_method)
    if body.llm_provider is not None:
        await set_setting(db, "llm_provider", body.llm_provider)
    if body.llm_model is not None:
        await set_setting(db, "llm_model", body.llm_model)
    if body.pii_anonymization is not None:
        await set_setting(db, "pii_anonymization", "true" if body.pii_anonymization else "false")
    if body.asr_api_url is not None:
        await set_setting(db, "asr_api_url", body.asr_api_url)
    if body.asr_api_key:
        await set_setting(db, "asr_api_key", body.asr_api_key)
    if body.openai_api_key:
        await set_setting(db, "openai_api_key", body.openai_api_key)
    if body.gemini_api_key:
        await set_setting(db, "gemini_api_key", body.gemini_api_key)
    if body.ollama_base_url is not None:
        await set_setting(db, "ollama_base_url", body.ollama_base_url)
    if body.asr_max_parallel is not None:
        await set_setting(db, "asr_max_parallel", str(max(1, min(8, body.asr_max_parallel))))
    if body.asr_http_timeout_sec is not None:
        await set_setting(db, "asr_http_timeout_sec", str(max(60, min(7200, body.asr_http_timeout_sec))))
    if body.playground_sequential is not None:
        await set_setting(db, "playground_sequential", "true" if body.playground_sequential else "false")
    if body.celery_worker_concurrency is not None:
        await set_setting(db, "celery_worker_concurrency", str(max(1, min(8, body.celery_worker_concurrency))))
    return MessageOut(message="Settings saved")


@router.get("/webitel", response_model=WebitelSettings)
async def get_webitel_settings(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    days_raw = await get_setting(db, "webitel_sync_days", "[0,1,2,3,4]")
    try:
        days = json.loads(days_raw)
    except json.JSONDecodeError:
        days = [0, 1, 2, 3, 4]
    return WebitelSettings(
        api_url=await get_setting(db, "webitel_api_url"),
        access_token=None,
        sync_cron=await get_setting(db, "webitel_sync_cron", "*/30 * * * *"),
        sync_days=days,
        sync_time_from=await get_setting(db, "webitel_sync_time_from", "09:00"),
        sync_time_to=await get_setting(db, "webitel_sync_time_to", "18:00"),
    )


@router.put("/webitel", response_model=MessageOut)
async def update_webitel_settings(
    body: WebitelSettings, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)
):
    await set_setting(db, "webitel_api_url", body.api_url)
    if body.access_token:
        await set_setting(db, "webitel_access_token", body.access_token)
    await set_setting(db, "webitel_sync_cron", body.sync_cron)
    await set_setting(db, "webitel_sync_days", json.dumps(body.sync_days))
    await set_setting(db, "webitel_sync_time_from", body.sync_time_from)
    await set_setting(db, "webitel_sync_time_to", body.sync_time_to)
    return MessageOut(message="Webitel settings saved")


@router.post("/webitel/test", response_model=dict)
async def test_webitel(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    url = await get_setting(db, "webitel_api_url")
    token = await get_setting(db, "webitel_access_token")
    client = WebitelClient(url, token)
    ok = await client.test_connection()
    return {"ok": ok, "message": "OK" if ok else "Не удалось подключиться"}


@router.get("/webitel/db", response_model=WebitelDbSettings)
async def get_webitel_db(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return WebitelDbSettings(
        host=await get_setting(db, "webitel_db_host"),
        port=int(await get_setting(db, "webitel_db_port", "5432")),
        database=await get_setting(db, "webitel_db_name", "webitel"),
        user=await get_setting(db, "webitel_db_user"),
        password=None,
    )


@router.put("/webitel/db", response_model=MessageOut)
async def update_webitel_db(
    body: WebitelDbSettings, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)
):
    await set_setting(db, "webitel_db_host", body.host)
    await set_setting(db, "webitel_db_port", str(body.port))
    await set_setting(db, "webitel_db_name", body.database)
    await set_setting(db, "webitel_db_user", body.user)
    if body.password:
        await set_setting(db, "webitel_db_password", body.password)
    return MessageOut(message="Webitel DB settings saved")


@router.post("/webitel/db/test", response_model=dict)
async def test_webitel_db_endpoint(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    ok, msg = test_webitel_db(
        await get_setting(db, "webitel_db_host"),
        int(await get_setting(db, "webitel_db_port", "5432")),
        await get_setting(db, "webitel_db_name", "webitel"),
        await get_setting(db, "webitel_db_user"),
        await get_setting(db, "webitel_db_password"),
    )
    return {"ok": ok, "message": msg}


@router.get("/automation", response_model=AutomationRuleOut)
async def get_automation(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(select(AutomationRule).limit(1))
    rule = result.scalar_one_or_none()
    if not rule:
        rule = AutomationRule(is_enabled=True, schedule_cron="*/30 * * * *", batch_size=10, active_days=[0, 1, 2, 3, 4])
        db.add(rule)
        await db.flush()
    return rule


@router.put("/automation", response_model=AutomationRuleOut)
async def update_automation(
    body: AutomationRuleUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)
):
    result = await db.execute(select(AutomationRule).limit(1))
    rule = result.scalar_one_or_none()
    if not rule:
        rule = AutomationRule()
        db.add(rule)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.flush()
    return rule


@router.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("/users", response_model=UserOut)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)):
    existing = await db.execute(select(User).where(User.login == body.login))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Login exists")
    user = User(
        login=body.login,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    await db.flush()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.password_hash = hash_password(body.password)
    return user
