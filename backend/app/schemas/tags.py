from datetime import datetime

from pydantic import BaseModel, Field


class TagOut(BaseModel):
    id: int
    name: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
