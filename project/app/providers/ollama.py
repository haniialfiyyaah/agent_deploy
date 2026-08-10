"""Ollama native `/api/chat` adapter with JSON and NDJSON support."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from time import perf_counter

import httpx

from app.providers.base import Completion, ProviderError, ProviderEvent
from app.schemas import ProviderHealth, ProviderMessage


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    async def health(self) -> ProviderHealth:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            models = {
                item.get("name")
                for item in response.json().get("models", [])
                if item.get("name")
            }
            ready = self.model in models
            detail = (
                "Configured model is available."
                if ready
                else f"Configured model '{self.model}' is not present."
            )
        except (httpx.HTTPError, ValueError) as exc:
            ready = False
            detail = f"Ollama is unavailable: {type(exc).__name__}."
        return ProviderHealth(
            ready=ready,
            provider=self.name,
            model=self.model,
            detail=detail,
        )

    async def complete(self, messages: list[ProviderMessage]) -> Completion:
        started = perf_counter()
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": [message.model_dump() for message in messages],
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return Completion(
                text=payload.get("message", {}).get("content", ""),
                input_tokens=payload.get("prompt_eval_count"),
                output_tokens=payload.get("eval_count"),
                duration_ms=payload.get("total_duration", 0) / 1_000_000
                or (perf_counter() - started) * 1000,
                finish_reason=payload.get("done_reason", "stop"),
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderError(f"Ollama completion failed: {type(exc).__name__}") from exc

    async def stream(
        self,
        messages: list[ProviderMessage],
    ) -> AsyncIterator[ProviderEvent]:
        try:
            async with self._client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": [message.model_dump() for message in messages],
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    payload = json.loads(line)
                    delta = payload.get("message", {}).get("content", "")
                    if delta:
                        yield ProviderEvent(kind="delta", delta=delta)
                    if payload.get("done"):
                        yield ProviderEvent(
                            kind="usage",
                            input_tokens=payload.get("prompt_eval_count"),
                            output_tokens=payload.get("eval_count"),
                            duration_ms=payload.get("total_duration", 0) / 1_000_000,
                            finish_reason=payload.get("done_reason", "stop"),
                        )
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Ollama stream failed: {type(exc).__name__}") from exc

    async def close(self) -> None:
        await self._client.aclose()
