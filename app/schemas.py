from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


Category = Literal["delivery", "returns", "damage", "warranty", "order_status", "general"]
RunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class RunCreate(BaseModel):
    message: str = Field(min_length=3, max_length=4000)
    customer_id: str | None = Field(default=None, pattern=r"^CUST-[0-9]{3}$")
    authenticated: bool = False
    category: Category = "general"
    allow_ticket_creation: bool = False
    expected_document_ids: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_identity(self) -> "RunCreate":
        if self.authenticated and not self.customer_id:
            raise ValueError("customer_id is required when authenticated is true")
        if self.allow_ticket_creation and not self.authenticated:
            raise ValueError("ticket creation requires an authenticated customer")
        return self


class RunAccepted(BaseModel):
    run_id: str
    status: RunStatus
    status_url: str
    events_url: str


class CancellationResponse(BaseModel):
    run_id: str
    accepted: bool
    status: RunStatus
