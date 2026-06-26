from fastapi import APIRouter

from app.api import (
    auth,
    calls,
    dashboard,
    health,
    operators,
    playground,
    research,
    scenarios,
    settings,
    tags,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(calls.router, prefix="/calls", tags=["calls"])
api_router.include_router(research.router, prefix="/research", tags=["research"])
api_router.include_router(operators.router, prefix="/operators", tags=["operators"])
api_router.include_router(scenarios.router, prefix="/scenarios", tags=["scenarios"])
api_router.include_router(playground.router, prefix="/playground", tags=["playground"])
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
