from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.models import Criterion, Scenario
from app.schemas.common import Paginated
from app.schemas.scenarios import ScenarioCreate, ScenarioOut, ScenarioUpdate


def _to_out(s: Scenario) -> ScenarioOut:
    return ScenarioOut(
        id=s.id,
        name=s.name,
        system_prompt=s.system_prompt,
        llm_model=s.llm_model,
        is_active=s.is_active,
        updated_at=s.updated_at,
        criteria=s.criteria,
        criteria_count=len(s.criteria),
    )


class ScenarioService:
    async def _load(self, db: AsyncSession, scenario_id: int) -> Scenario:
        result = await db.execute(
            select(Scenario).where(Scenario.id == scenario_id).options(selectinload(Scenario.criteria))
        )
        scenario = result.scalar_one_or_none()
        if not scenario:
            raise AppError.not_found("Scenario not found")
        return scenario

    async def list_scenarios(
        self, db: AsyncSession, *, page: int, page_size: int
    ) -> Paginated[ScenarioOut]:
        total = await db.scalar(select(func.count()).select_from(Scenario)) or 0
        result = await db.execute(
            select(Scenario)
            .options(selectinload(Scenario.criteria))
            .order_by(Scenario.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [_to_out(s) for s in result.scalars().all()]
        return Paginated(items=items, total=total, page=page, page_size=page_size)

    async def create(self, db: AsyncSession, body: ScenarioCreate) -> ScenarioOut:
        scenario = Scenario(
            name=body.name,
            system_prompt=body.system_prompt,
            llm_model=body.llm_model,
            is_active=body.is_active,
        )
        db.add(scenario)
        await db.flush()
        for i, c in enumerate(body.criteria):
            db.add(
                Criterion(
                    scenario_id=scenario.id,
                    key=c.key,
                    name=c.name,
                    weight_percent=c.weight_percent,
                    max_score=c.max_score,
                    prompt=c.prompt,
                    sort_order=c.sort_order or i,
                )
            )
        await db.flush()
        return _to_out(await self._load(db, scenario.id))

    async def get(self, db: AsyncSession, scenario_id: int) -> ScenarioOut:
        return _to_out(await self._load(db, scenario_id))

    async def update(self, db: AsyncSession, scenario_id: int, body: ScenarioUpdate) -> ScenarioOut:
        scenario = await self._load(db, scenario_id)
        if body.name is not None:
            scenario.name = body.name
        if body.system_prompt is not None:
            scenario.system_prompt = body.system_prompt
        if body.llm_model is not None:
            scenario.llm_model = body.llm_model
        if body.is_active is not None:
            scenario.is_active = body.is_active
        if body.criteria is not None:
            for c in list(scenario.criteria):
                await db.delete(c)
            for i, c in enumerate(body.criteria):
                db.add(
                    Criterion(
                        scenario_id=scenario.id,
                        key=c.key,
                        name=c.name,
                        weight_percent=c.weight_percent,
                        max_score=c.max_score,
                        prompt=c.prompt,
                        sort_order=c.sort_order or i,
                    )
                )
        await db.flush()
        return _to_out(await self._load(db, scenario.id))

    async def delete(self, db: AsyncSession, scenario_id: int) -> None:
        result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
        scenario = result.scalar_one_or_none()
        if not scenario:
            raise AppError.not_found("Scenario not found")
        await db.delete(scenario)

    async def copy(self, db: AsyncSession, scenario_id: int) -> ScenarioOut:
        src = await self._load(db, scenario_id)
        copy = Scenario(
            name=f"{src.name} (копия)",
            system_prompt=src.system_prompt,
            llm_model=src.llm_model,
            is_active=False,
        )
        db.add(copy)
        await db.flush()
        for c in src.criteria:
            db.add(
                Criterion(
                    scenario_id=copy.id,
                    key=c.key,
                    name=c.name,
                    weight_percent=c.weight_percent,
                    max_score=c.max_score,
                    prompt=c.prompt,
                    sort_order=c.sort_order,
                )
            )
        await db.flush()
        return _to_out(await self._load(db, copy.id))

    async def export_payload(self, db: AsyncSession, scenario_id: int) -> dict:
        scenario = await self._load(db, scenario_id)
        return {
            "name": scenario.name,
            "system_prompt": scenario.system_prompt,
            "llm_model": scenario.llm_model,
            "criteria": [
                {
                    "key": c.key,
                    "name": c.name,
                    "weight_percent": c.weight_percent,
                    "max_score": c.max_score,
                    "prompt": c.prompt,
                }
                for c in scenario.criteria
            ],
        }


scenario_service = ScenarioService()
