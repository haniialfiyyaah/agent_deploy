"""Pydantic contracts shared by API, storage, context, and providers."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Role = Literal["system", "user", "assistant"]
MessageStatus = Literal["in_progress", "completed", "cancelled", "error"]


class ThreadCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class MessageRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    thread_id: str
    position: int
    role: Role
    content: str
    status: MessageStatus
    estimated_tokens: int = 0
    created_at: datetime
    updated_at: datetime


class ThreadSummary(BaseModel):
    id: str
    owner_id: str
    title: str
    summary: str
    summarized_through_position: int
    created_at: datetime
    updated_at: datetime


class ThreadDetail(ThreadSummary):
    messages: list[MessageRecord]


class ProviderMessage(BaseModel):
    role: Role
    content: str


class ContextInfo(BaseModel):
    estimated_input_tokens: int
    compacted: bool
    summarized_through_position: int
    included_message_count: int


class UsageInfo(BaseModel):
    input_tokens: int
    output_tokens: int
    duration_ms: float
    time_to_first_token_ms: float | None = None


class MessageResponse(BaseModel):
    thread_id: str
    user_message: MessageRecord
    assistant_message: MessageRecord
    usage: UsageInfo
    context: ContextInfo


class ProviderHealth(BaseModel):
    ready: bool
    provider: str
    model: str
    detail: str
