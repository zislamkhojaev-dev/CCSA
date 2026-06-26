import asyncio

from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models import AutomationRule, Criterion, Scenario, User
from app.services.settings_store import set_setting


async def seed() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.login == settings.seed_admin_login))
        if not result.scalar_one_or_none():
            db.add(
                User(
                    login=settings.seed_admin_login,
                    password_hash=hash_password(settings.seed_admin_password),
                    full_name="Administrator",
                    role="admin",
                )
            )

        result = await db.execute(select(Scenario).limit(1))
        if not result.scalar_one_or_none():
            scenario = Scenario(
                name="Входящая линия техподдержки",
                system_prompt="Ты валидатор качества работы службы поддержки. Оцени разговор по критериям.",
                llm_model="gpt-4o-mini",
                is_active=True,
            )
            db.add(scenario)
            await db.flush()
            db.add_all(
                [
                    Criterion(
                        scenario_id=scenario.id,
                        key="greeting",
                        name="Приветствие",
                        weight_percent=15,
                        max_score=15,
                        prompt="Проверь стандартное приветствие оператора.",
                        sort_order=0,
                    ),
                    Criterion(
                        scenario_id=scenario.id,
                        key="politeness",
                        name="Вежливость",
                        weight_percent=25,
                        max_score=25,
                        prompt="Оцени вежливый тон на протяжении разговора.",
                        sort_order=1,
                    ),
                    Criterion(
                        scenario_id=scenario.id,
                        key="need_discovery",
                        name="Выявление потребности",
                        weight_percent=30,
                        max_score=30,
                        prompt="Задал ли оператор минимум 2 уточняющих вопроса о проблеме?",
                        sort_order=2,
                    ),
                    Criterion(
                        scenario_id=scenario.id,
                        key="closing",
                        name="Завершение",
                        weight_percent=30,
                        max_score=30,
                        prompt="Корректно ли завершён разговор, предложена ли помощь?",
                        sort_order=3,
                    ),
                ]
            )

        result = await db.execute(select(AutomationRule).limit(1))
        if not result.scalar_one_or_none():
            db.add(
                AutomationRule(
                    is_enabled=True,
                    schedule_cron="*/30 * * * *",
                    batch_size=10,
                    active_days=[0, 1, 2, 3, 4],
                    time_from="09:00",
                    time_to="18:00",
                )
            )

        if settings.openai_api_key:
            await set_setting(db, "openai_api_key", settings.openai_api_key)
        if settings.webitel_api_url:
            await set_setting(db, "webitel_api_url", settings.webitel_api_url)
        if settings.webitel_access_token:
            await set_setting(db, "webitel_access_token", settings.webitel_access_token)

        await db.commit()
        print("Seed completed.")


if __name__ == "__main__":
    asyncio.run(seed())
