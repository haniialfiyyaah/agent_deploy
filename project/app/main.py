"""FastAPI application for a thread-aware local LLM gateway."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.context import ContextBuilder, ContextOverflowError, estimate_tokens
from app.providers import LLMProvider, create_provider
from app.providers.base import ProviderError
from app.schemas import (
    MessageCreate,
    MessageResponse,
    ProviderHealth,
    ThreadCreate,
    ThreadDetail,
    ThreadSummary,
    UsageInfo,
)
from app.settings import Settings, get_settings
from app.store import ConversationStore
from app.telemetry import Telemetry


OwnerId = Annotated[str, Header(alias="X-User-ID", min_length=1, max_length=120)]
STATIC_DIR = Path(__file__).parent / "static"


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def create_app(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    """Create an isolated application, suitable for tests and local serving."""

    configured_settings = settings or get_settings()
    configured_provider = provider or create_provider(configured_settings)
    store = ConversationStore(configured_settings.database_path)
    context_builder = ContextBuilder(configured_settings)
    telemetry = Telemetry()
    thread_locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        store.initialize()
        application.state.settings = configured_settings
        application.state.provider = configured_provider
        application.state.store = store
        application.state.context_builder = context_builder
        application.state.telemetry = telemetry
        try:
            yield
        finally:
            await configured_provider.close()

    application = FastAPI(
        title=configured_settings.app_name,
        version="2.0.0",
        description=(
            "Application-owned conversation state with local LLM provider adapters, "
            "complete responses, SSE streaming, and Prometheus metrics."
        ),
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def require_thread(owner_id: str, thread_id: str) -> ThreadSummary:
        thread = store.get_thread(owner_id, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found.")
        return thread

    async def acquire_thread(thread_id: str) -> asyncio.Lock:
        lock = thread_locks.setdefault(thread_id, asyncio.Lock())
        if lock.locked():
            raise HTTPException(
                status_code=409,
                detail="This thread already has a generation in progress.",
            )
        await lock.acquire()
        return lock

    def enforce_message_limit(content: str) -> None:
        if len(content) > configured_settings.max_message_characters:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Message exceeds the configured limit of "
                    f"{configured_settings.max_message_characters} characters."
                ),
            )

    @application.get("/", include_in_schema=False)
    async def browser_client() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @application.get(
        "/health/ready",
        response_model=ProviderHealth,
        tags=["health"],
    )
    async def readiness() -> ProviderHealth | JSONResponse:
        health = await configured_provider.health()
        telemetry.provider_ready.labels(
            configured_provider.name,
            configured_provider.model,
        ).set(1 if health.ready else 0)
        if not health.ready:
            return JSONResponse(status_code=503, content=health.model_dump())
        return health

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            generate_latest(telemetry.registry),
            media_type=CONTENT_TYPE_LATEST,
        )

    @application.post(
        "/v1/threads",
        response_model=ThreadSummary,
        status_code=status.HTTP_201_CREATED,
        tags=["threads"],
    )
    async def create_thread(payload: ThreadCreate, owner_id: OwnerId) -> ThreadSummary:
        return store.create_thread(owner_id, payload.title)

    @application.get(
        "/v1/threads",
        response_model=list[ThreadSummary],
        tags=["threads"],
    )
    async def list_threads(owner_id: OwnerId) -> list[ThreadSummary]:
        return store.list_threads(owner_id)

    @application.get(
        "/v1/threads/{thread_id}",
        response_model=ThreadDetail,
        tags=["threads"],
    )
    async def get_thread(thread_id: str, owner_id: OwnerId) -> ThreadDetail:
        detail = store.get_thread_detail(owner_id, thread_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Thread not found.")
        return detail

    @application.delete(
        "/v1/threads/{thread_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["threads"],
    )
    async def delete_thread(thread_id: str, owner_id: OwnerId) -> Response:
        active_lock = thread_locks.get(thread_id)
        if active_lock is not None and active_lock.locked():
            raise HTTPException(
                status_code=409,
                detail="This thread already has a generation in progress.",
            )
        if not store.delete_thread(owner_id, thread_id):
            raise HTTPException(status_code=404, detail="Thread not found.")
        thread_locks.pop(thread_id, None)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.post(
        "/v1/threads/{thread_id}/messages",
        response_model=MessageResponse,
        tags=["messages"],
    )
    async def create_message(
        thread_id: str,
        payload: MessageCreate,
        owner_id: OwnerId,
    ) -> MessageResponse:
        enforce_message_limit(payload.content)
        thread = require_thread(owner_id, thread_id)
        thread_lock = await acquire_thread(thread_id)
        started = perf_counter()
        try:
            user_message = store.add_message(
                thread_id,
                "user",
                payload.content,
                estimated_tokens=estimate_tokens(payload.content),
            )
            prepared = context_builder.prepare(store, thread)
            if prepared.info.compacted:
                telemetry.context_compactions.labels(configured_provider.name).inc()
            completion = await configured_provider.complete(prepared.messages)
            output_tokens = completion.output_tokens or estimate_tokens(completion.text)
            input_tokens = completion.input_tokens or prepared.info.estimated_input_tokens
            assistant_message = store.add_message(
                thread_id,
                "assistant",
                completion.text,
                estimated_tokens=output_tokens,
            )
        except ContextOverflowError as exc:
            telemetry.requests.labels(
                "complete", configured_provider.name, "context_overflow"
            ).inc()
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except (ProviderError, RuntimeError) as exc:
            store.add_message(thread_id, "assistant", "", status="error")
            telemetry.requests.labels(
                "complete", configured_provider.name, "provider_error"
            ).inc()
            raise HTTPException(
                status_code=503,
                detail="The configured model provider could not complete the request.",
            ) from exc
        finally:
            thread_lock.release()

        duration = perf_counter() - started
        telemetry.requests.labels("complete", configured_provider.name, "success").inc()
        telemetry.request_duration.labels("complete", configured_provider.name).observe(
            duration
        )
        telemetry.tokens.labels("input", configured_provider.name).inc(input_tokens)
        telemetry.tokens.labels("output", configured_provider.name).inc(output_tokens)
        return MessageResponse(
            thread_id=thread_id,
            user_message=user_message,
            assistant_message=assistant_message,
            usage=UsageInfo(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=completion.duration_ms or duration * 1000,
            ),
            context=prepared.info,
        )

    @application.post(
        "/v1/threads/{thread_id}/messages/stream",
        tags=["messages"],
        responses={200: {"content": {"text/event-stream": {}}}},
    )
    async def stream_message(
        thread_id: str,
        payload: MessageCreate,
        owner_id: OwnerId,
        request: Request,
    ) -> StreamingResponse:
        enforce_message_limit(payload.content)
        thread = require_thread(owner_id, thread_id)
        thread_lock = await acquire_thread(thread_id)
        try:
            user_message = store.add_message(
                thread_id,
                "user",
                payload.content,
                estimated_tokens=estimate_tokens(payload.content),
            )
            prepared = context_builder.prepare(store, thread)
        except ContextOverflowError as exc:
            thread_lock.release()
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except Exception:
            thread_lock.release()
            raise

        assistant_message = store.add_message(
            thread_id,
            "assistant",
            "",
            status="in_progress",
        )

        async def event_stream() -> AsyncIterator[str]:
            started = perf_counter()
            first_delta_at: float | None = None
            text_parts: list[str] = []
            input_tokens = prepared.info.estimated_input_tokens
            output_tokens = 0
            provider_duration_ms = 0.0
            telemetry.active_streams.labels(configured_provider.name).inc()
            yield _sse(
                "message.start",
                {
                    "thread_id": thread_id,
                    "user_message_id": user_message.id,
                    "assistant_message_id": assistant_message.id,
                    "provider": configured_provider.name,
                    "model": configured_provider.model,
                    "context": prepared.info.model_dump(),
                },
            )
            if prepared.info.compacted:
                telemetry.context_compactions.labels(configured_provider.name).inc()
                yield _sse("context.compacted", prepared.info.model_dump())
            try:
                async for event in configured_provider.stream(prepared.messages):
                    if await request.is_disconnected():
                        raise asyncio.CancelledError
                    if event.kind == "delta" and event.delta:
                        if first_delta_at is None:
                            first_delta_at = perf_counter()
                            telemetry.time_to_first_token.labels(
                                configured_provider.name
                            ).observe(first_delta_at - started)
                        text_parts.append(event.delta)
                        yield _sse("message.delta", {"delta": event.delta})
                    elif event.kind == "usage":
                        input_tokens = event.input_tokens or input_tokens
                        output_tokens = event.output_tokens or output_tokens
                        provider_duration_ms = event.duration_ms or provider_duration_ms

                text = "".join(text_parts).rstrip()
                output_tokens = output_tokens or estimate_tokens(text)
                completed = store.update_message(
                    assistant_message.id,
                    content=text,
                    status="completed",
                    estimated_tokens=output_tokens,
                )
                elapsed = perf_counter() - started
                ttft_ms = (
                    (first_delta_at - started) * 1000
                    if first_delta_at is not None
                    else None
                )
                usage = UsageInfo(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=provider_duration_ms or elapsed * 1000,
                    time_to_first_token_ms=ttft_ms,
                )
                telemetry.requests.labels(
                    "stream", configured_provider.name, "success"
                ).inc()
                telemetry.request_duration.labels(
                    "stream", configured_provider.name
                ).observe(elapsed)
                telemetry.tokens.labels("input", configured_provider.name).inc(
                    input_tokens
                )
                telemetry.tokens.labels("output", configured_provider.name).inc(
                    output_tokens
                )
                yield _sse("message.completed", completed.model_dump(mode="json"))
                yield _sse("usage", usage.model_dump())
                yield _sse("done", {})
            except asyncio.CancelledError:
                partial = "".join(text_parts).rstrip()
                store.update_message(
                    assistant_message.id,
                    content=partial,
                    status="cancelled",
                    estimated_tokens=estimate_tokens(partial),
                )
                telemetry.cancelled_streams.labels(configured_provider.name).inc()
                telemetry.requests.labels(
                    "stream", configured_provider.name, "cancelled"
                ).inc()
                raise
            except (ProviderError, RuntimeError) as exc:
                partial = "".join(text_parts).rstrip()
                store.update_message(
                    assistant_message.id,
                    content=partial,
                    status="error",
                    estimated_tokens=estimate_tokens(partial),
                )
                telemetry.requests.labels(
                    "stream", configured_provider.name, "provider_error"
                ).inc()
                yield _sse(
                    "error",
                    {
                        "code": "provider_error",
                        "message": "The model provider stopped before completion.",
                    },
                )
                yield _sse("done", {})
            finally:
                telemetry.active_streams.labels(configured_provider.name).dec()
                thread_lock.release()

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return application


app = create_app()
