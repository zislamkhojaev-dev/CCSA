from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.readiness import collect_readiness

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    ok, checks = await collect_readiness()
    body = {"status": "ready" if ok else "not_ready", "checks": checks}
    if not ok:
        return JSONResponse(status_code=503, content=body)
    return body
