"""Deterministic provider used for tests and no-download classroom setup."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from time import perf_counter

from app.context import estimate_tokens
from app.providers.base import Completion, ProviderEvent
from app.schemas import ProviderHealth, ProviderMessage


class MockProvider:
    name = "mock"
    model = "deterministic-lab-model"

    def __init__(self, delay_seconds: float = 0.0, fail_after_deltas: int | None = None) -> None:
        self.delay_seconds = delay_seconds
        self.fail_after_deltas = fail_after_deltas

    def _response(self, messages: list[ProviderMessage]) -> str:
        user_content = next(
            (message.content for message in reversed(messages) if message.role == "user"),
            "",
        )
        return (
            "Mock response: the gateway received your message and built a bounded "
            f"context. Request preview: {user_content[:120]}"
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            ready=True,
            provider=self.name,
            model=self.model,
            detail="Deterministic provider is ready.",
        )

    async def complete(self, messages: list[ProviderMessage]) -> Completion:
        started = perf_counter()
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        text = self._response(messages)
        return Completion(
            text=text,
            input_tokens=sum(estimate_tokens(message.content) for message in messages),
            output_tokens=estimate_tokens(text),
            duration_ms=(perf_counter() - started) * 1000,
        )

    async def stream(
        self,
        messages: list[ProviderMessage],
    ) -> AsyncIterator[ProviderEvent]:
        started = perf_counter()
        text = self._response(messages)
        chunks = [word + " " for word in text.split()]
        for index, chunk in enumerate(chunks):
            if self.fail_after_deltas is not None and index >= self.fail_after_deltas:
                raise RuntimeError("Injected mock provider failure")
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            yield ProviderEvent(kind="delta", delta=chunk)
        yield ProviderEvent(
            kind="usage",
            input_tokens=sum(estimate_tokens(message.content) for message in messages),
            output_tokens=estimate_tokens(text),
            duration_ms=(perf_counter() - started) * 1000,
            finish_reason="stop",
        )

    async def close(self) -> None:
        return None
