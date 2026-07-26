from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Criterion, Scenario, User
from app.schemas.common import MessageOut
from app.schemas.scenarios import ScenarioCreate, ScenarioOut, ScenarioUpdate

router = APIRouter()


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


async def _load_scenario_out(db: AsyncSession, scenario_id: int) -> ScenarioOut:
    """Reload scenario after flush — partial refresh expires columns and breaks async lazy load."""
    result = await db.execute(
        select(Scenario).where(Scenario.id == scenario_id).options(selectinload(Scenario.criteria))
    )
    scenario = result.scalar_one()
    return _to_out(scenario)


@router.get("", response_model=list[ScenarioOut])
async def list_scenarios(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(
        select(Scenario).options(selectinload(Scenario.criteria)).order_by(Scenario.updated_at.desc())
    )
    return [_to_out(s) for s in result.scalars().all()]


@router.post("", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    body: ScenarioCreate, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
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
    return await _load_scenario_out(db, scenario.id)


@router.get("/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(scenario_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(
        select(Scenario).where(Scenario.id == scenario_id).options(selectinload(Scenario.criteria))
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return _to_out(scenario)


@router.put("/{scenario_id}", response_model=ScenarioOut)
async def update_scenario(
    scenario_id: int,
    body: ScenarioUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Scenario).where(Scenario.id == scenario_id).options(selectinload(Scenario.criteria))
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

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
    return await _load_scenario_out(db, scenario.id)


@router.delete("/{scenario_id}", response_model=MessageOut)
async def delete_scenario(
    scenario_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    await db.delete(scenario)
    return MessageOut(message="Deleted")


@router.post("/{scenario_id}/copy", response_model=ScenarioOut)
async def copy_scenario(
    scenario_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Scenario).where(Scenario.id == scenario_id).options(selectinload(Scenario.criteria))
    )
    src = result.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Scenario not found")

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
    return await _load_scenario_out(db, copy.id)


@router.get("/{scenario_id}/export")
async def export_scenario(scenario_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(
        select(Scenario).where(Scenario.id == scenario_id).options(selectinload(Scenario.criteria))
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    data = {
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
    return JSONResponse(content=data, headers={"Content-Disposition": f'attachment; filename="scenario_{scenario_id}.json"'})
