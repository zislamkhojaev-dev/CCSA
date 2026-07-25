from pydantic import BaseModel


class OperatorOut(BaseModel):
    id: int
    webitel_id: str | None
    full_name: str
    team_name: str | None
    is_active: bool
    calls_count: int = 0
    avg_score: float | None = None

    model_config = {"from_attributes": True}


class OperatorSyncOut(BaseModel):
    message: str
    created: int = 0
    found: int = 0
    calls_scanned: int = 0
