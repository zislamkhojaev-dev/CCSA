from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_admin_user, get_current_user
from app.database import get_db
from app.models import User
from app.schemas.common import MessageOut, Paginated
from app.schemas.scenarios import ScenarioCreate, ScenarioOut, ScenarioUpdate
from app.services.scenario_service import scenario_service

router = APIRouter()


@router.get("", response_model=Paginated[ScenarioOut])
async def list_scenarios(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await scenario_service.list_scenarios(db, page=page, page_size=page_size)


@router.post("", response_model=ScenarioOut, status_code=201)
async def create_scenario(
    body: ScenarioCreate, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    return await scenario_service.create(db, body)


@router.get("/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(scenario_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await scenario_service.get(db, scenario_id)


@router.put("/{scenario_id}", response_model=ScenarioOut)
async def update_scenario(
    scenario_id: int,
    body: ScenarioUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await scenario_service.update(db, scenario_id, body)


@router.delete("/{scenario_id}", response_model=MessageOut)
async def delete_scenario(
    scenario_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_admin_user)
):
    await scenario_service.delete(db, scenario_id)
    return MessageOut(message="Deleted")


@router.post("/{scenario_id}/copy", response_model=ScenarioOut)
async def copy_scenario(
    scenario_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    return await scenario_service.copy(db, scenario_id)


@router.get("/{scenario_id}/export")
async def export_scenario(scenario_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    data = await scenario_service.export_payload(db, scenario_id)
    return JSONResponse(
        content=data, headers={"Content-Disposition": f'attachment; filename="scenario_{scenario_id}.json"'}
    )
