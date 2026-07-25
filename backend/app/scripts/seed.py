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
                name="Входящие звонки — контроль качества",
                system_prompt=(
                    "Ты — эксперт по контролю качества входящей линии колл-центра. "
                    "Оцени транскрипт: оператор принимает обращение, выясняет потребность, "
                    "предлагает решение и завершает разговор. Опирайся только на факты из текста."
                ),
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
                        weight_percent=10,
                        max_score=100,
                        prompt="Стандартное приветствие: компания, имя оператора, предложение помощи.",
                        sort_order=0,
                    ),
                    Criterion(
                        scenario_id=scenario.id,
                        key="politeness",
                        name="Вежливость",
                        weight_percent=15,
                        max_score=100,
                        prompt="Уважительный тон на протяжении разговора, без грубости и перебиваний.",
                        sort_order=1,
                    ),
                    Criterion(
                        scenario_id=scenario.id,
                        key="need_discovery",
                        name="Выявление потребности",
                        weight_percent=35,
                        max_score=100,
                        prompt="Минимум 2 уточняющих вопроса и резюме потребности клиента.",
                        sort_order=2,
                    ),
                    Criterion(
                        scenario_id=scenario.id,
                        key="solution_proposal",
                        name="Предложение решения проблемы",
                        weight_percent=30,
                        max_score=100,
                        prompt="Конкретный план действий, сроки и следующие шаги для клиента.",
                        sort_order=3,
                    ),
                    Criterion(
                        scenario_id=scenario.id,
                        key="closing",
                        name="Завершение разговора",
                        weight_percent=10,
                        max_score=100,
                        prompt="Итог договорённостей, вопрос о доп. помощи, благодарность и прощание.",
                        sort_order=4,
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
