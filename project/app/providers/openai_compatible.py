"""OpenAI-compatible chat-completions adapter, suitable for LM Studio."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from time import perf_counter

import httpx

from app.providers.base import Completion, ProviderError, ProviderEvent
from app.schemas import ProviderHealth, ProviderMessage


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )

    async def health(self) -> ProviderHealth:
        try:
            response = await self._client.get("/models")
            response.raise_for_status()
            identifiers = {
                item.get("id")
                for item in response.json().get("data", [])
                if item.get("id")
            }
            ready = self.model in identifiers
            detail = (
                "Configured model is available."
                if ready
                else f"Configured model '{self.model}' is not present."
            )
        except (httpx.HTTPError, ValueError) as exc:
            ready = False
            detail = f"OpenAI-compatible runtime is unavailable: {type(exc).__name__}."
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
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [message.model_dump() for message in messages],
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            choice = payload["choices"][0]
            usage = payload.get("usage", {})
            return Completion(
                text=choice["message"]["content"] or "",
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                duration_ms=(perf_counter() - started) * 1000,
                finish_reason=choice.get("finish_reason", "stop"),
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            raise ProviderError(
                f"OpenAI-compatible completion failed: {type(exc).__name__}"
            ) from exc

    async def stream(
        self,
        messages: list[ProviderMessage],
    ) -> AsyncIterator[ProviderEvent]:
        started = perf_counter()
        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [message.model_dump() for message in messages],
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    payload = json.loads(data)
                    choices = payload.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {}).get("content") or ""
                        if delta:
                            yield ProviderEvent(kind="delta", delta=delta)
                    usage = payload.get("usage")
                    if usage:
                        yield ProviderEvent(
                            kind="usage",
                            input_tokens=usage.get("prompt_tokens"),
                            output_tokens=usage.get("completion_tokens"),
                            duration_ms=(perf_counter() - started) * 1000,
                            finish_reason=(
                                choices[0].get("finish_reason") if choices else "stop"
                            ),
                        )
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(
                f"OpenAI-compatible stream failed: {type(exc).__name__}"
            ) from exc

    async def close(self) -> None:
        await self._client.aclose()
