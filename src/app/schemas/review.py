from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Review(BaseModel):
    review: str = Field(min_length=1, max_length=10_000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
