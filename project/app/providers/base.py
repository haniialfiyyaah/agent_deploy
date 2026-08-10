"""Provider-neutral LLM contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.schemas import ProviderHealth, ProviderMessage


class ProviderError(RuntimeError):
    """A bounded error raised when an inference provider cannot complete work."""


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: float = 0.0
    finish_reason: str = "stop"


@dataclass(frozen=True)
class ProviderEvent:
    kind: str
    delta: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: float | None = None
    finish_reason: str | None = None


class LLMProvider(Protocol):
    name: str
    model: str

    async def health(self) -> ProviderHealth: ...

    async def complete(self, messages: list[ProviderMessage]) -> Completion: ...

    def stream(self, messages: list[ProviderMessage]) -> AsyncIterator[ProviderEvent]: ...

    async def close(self) -> None: ...
