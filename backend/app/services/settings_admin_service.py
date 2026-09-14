from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_password
from app.models import AutomationRule, User
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.common import Paginated
from app.schemas.settings import AutomationRuleUpdate
from app.services.settings_store import get_setting
from app.services.webitel import WebitelClient
from app.services.webitel_db import webitel_db_adapter


class SettingsAdminService:
    async def list_users(self, db: AsyncSession, *, page: int, page_size: int) -> Paginated[UserOut]:
        total = await db.scalar(select(func.count()).select_from(User)) or 0
        result = await db.execute(
            select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        items = [UserOut.model_validate(u) for u in result.scalars().all()]
        return Paginated(items=items, total=total, page=page, page_size=page_size)

    async def create_user(self, db: AsyncSession, body: UserCreate) -> UserOut:
        existing = await db.execute(select(User).where(User.login == body.login))
        if existing.scalar_one_or_none():
            raise AppError.invalid("Login exists")
        user = User(
            login=body.login,
            password_hash=hash_password(body.password),
            full_name=body.full_name,
            role=body.role,
        )
        db.add(user)
        await db.flush()
        return UserOut.model_validate(user)

    async def update_user(self, db: AsyncSession, user_id: int, body: UserUpdate) -> UserOut:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise AppError.not_found("User not found")
        if body.full_name is not None:
            user.full_name = body.full_name
        if body.role is not None:
            user.role = body.role
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.password:
            user.password_hash = hash_password(body.password)
        return UserOut.model_validate(user)

    async def get_or_create_automation(self, db: AsyncSession) -> AutomationRule:
        result = await db.execute(select(AutomationRule).limit(1))
        rule = result.scalar_one_or_none()
        if not rule:
            rule = AutomationRule(
                is_enabled=True, schedule_cron="*/30 * * * *", batch_size=10, active_days=[0, 1, 2, 3, 4]
            )
            db.add(rule)
            await db.flush()
        return rule

    async def update_automation(self, db: AsyncSession, body: AutomationRuleUpdate) -> AutomationRule:
        rule = await self.get_or_create_automation(db)
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)
        await db.flush()
        return rule

    async def test_webitel(self, db: AsyncSession) -> dict:
        url = await get_setting(db, "webitel_api_url")
        token = await get_setting(db, "webitel_access_token")
        client = WebitelClient(url, token)
        ok = await client.test_connection()
        return {"ok": ok, "message": "OK" if ok else "Не удалось подключиться"}

    async def test_webitel_db(self, db: AsyncSession) -> dict:
        ok, msg = webitel_db_adapter.test_connection(
            await get_setting(db, "webitel_db_host"),
            int(await get_setting(db, "webitel_db_port", "5432")),
            await get_setting(db, "webitel_db_name", "webitel"),
            await get_setting(db, "webitel_db_user"),
            await get_setting(db, "webitel_db_password"),
        )
        return {"ok": ok, "message": msg}


settings_admin_service = SettingsAdminService()
