from pydantic import BaseModel, Field


class Ticket(BaseModel):
    name: str | None = Field(default=None, description="Customer's name, if provided")
    email: str | None = Field(default=None, description="Customer's email, if provided")
    issue: str = Field(description="Customer's complaint or issue")
