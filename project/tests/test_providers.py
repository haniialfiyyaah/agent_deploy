from __future__ import annotations

import json

import httpx
import pytest

from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.schemas import ProviderMessage


@pytest.mark.asyncio
async def test_ollama_parses_complete_and_ndjson_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "lab:latest"}]})
        payload = json.loads(request.content)
        if payload["stream"]:
            body = (
                '{"message":{"content":"Hello "},"done":false}\n'
                '{"message":{"content":"world"},"done":false}\n'
                '{"message":{"content":""},"done":true,'
                '"prompt_eval_count":7,"eval_count":2,"total_duration":1000000}\n'
            )
            return httpx.Response(200, text=body)
        return httpx.Response(
            200,
            json={
                "message": {"content": "Hello world"},
                "prompt_eval_count": 7,
                "eval_count": 2,
                "total_duration": 1_000_000,
                "done_reason": "stop",
            },
        )

    provider = OllamaProvider(
        "http://ollama",
        "lab:latest",
        5,
        transport=httpx.MockTransport(handler),
    )
    messages = [ProviderMessage(role="user", content="Hello")]
    try:
        assert (await provider.health()).ready is True
        completion = await provider.complete(messages)
        events = [event async for event in provider.stream(messages)]
    finally:
        await provider.close()

    assert completion.text == "Hello world"
    assert "".join(event.delta for event in events if event.kind == "delta") == "Hello world"
    assert events[-1].output_tokens == 2


@pytest.mark.asyncio
async def test_openai_compatible_parses_complete_and_sse_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "local-model"}]})
        payload = json.loads(request.content)
        if payload["stream"]:
            body = (
                'data: {"choices":[{"delta":{"content":"Hello "},'
                '"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{"content":"world"},'
                '"finish_reason":null}]}\n\n'
                'data: {"choices":[],"usage":{"prompt_tokens":7,'
                '"completion_tokens":2}}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, text=body)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "Hello world"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 7, "completion_tokens": 2},
            },
        )

    provider = OpenAICompatibleProvider(
        "http://runtime/v1",
        "local-model",
        "local-key",
        5,
        transport=httpx.MockTransport(handler),
    )
    messages = [ProviderMessage(role="user", content="Hello")]
    try:
        assert (await provider.health()).ready is True
        completion = await provider.complete(messages)
        events = [event async for event in provider.stream(messages)]
    finally:
        await provider.close()

    assert completion.text == "Hello world"
    assert "".join(event.delta for event in events if event.kind == "delta") == "Hello world"
    assert events[-1].input_tokens == 7
