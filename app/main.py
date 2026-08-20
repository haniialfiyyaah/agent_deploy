from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import CancellationResponse, RunAccepted, RunCreate
from app.service import RunManager, TERMINAL
from src.config import APP_DB, app_version, load_model_settings, readiness_forced_down
from src.models import AgentRequest
from src.setup_lab import setup


STATIC_DIR = Path(__file__).parent / "static"
manager = RunManager()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup(reset=False)
    yield


app = FastAPI(
    title="Northstar Agent Deployment API",
    version=app_version(),
    description="Production-serving lab for the Module 14 Northstar customer-support agent.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, object]:
    reasons: list[str] = []
    try:
        settings = load_model_settings()
    except RuntimeError as exc:
        settings = None
        reasons.append(str(exc))
    if not APP_DB.exists():
        reasons.append("Northstar database is not initialized")
    if readiness_forced_down():
        reasons.append("readiness failure is intentionally enabled")
    ready = not reasons
    payload: dict[str, object] = {
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "model": settings.agent_model if settings else "unconfigured",
        "version": app_version(),
        "reasons": reasons,
        "provider_probe": "not_called",
    }
    if not ready:
        raise HTTPException(status_code=503, detail=payload)
    return payload


@app.get("/version", tags=["operations"])
async def version() -> dict[str, str]:
    return {"app_version": app_version(), "agent": "northstar-baseline", "kb_version": "healthy"}


@app.post("/v1/runs", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED, tags=["runs"])
async def submit_run(payload: RunCreate) -> RunAccepted:
    try:
        settings = load_model_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    request = AgentRequest(
        message=payload.message,
        customer_id=payload.customer_id,
        authenticated=payload.authenticated,
        category=payload.category,
        allow_ticket_creation=payload.allow_ticket_creation,
        expected_document_ids=payload.expected_document_ids,
    )
    managed = manager.submit(request, settings)
    return RunAccepted(
        run_id=managed.run_id,
        status="queued",
        status_url=f"/v1/runs/{managed.run_id}",
        events_url=f"/v1/runs/{managed.run_id}/events",
    )


@app.get("/v1/runs/{run_id}", tags=["runs"])
async def get_run(run_id: str) -> dict[str, object]:
    snapshot = manager.snapshot(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return snapshot


@app.get("/v1/runs/{run_id}/events", tags=["runs"])
async def stream_events(
    run_id: str,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    if manager.get(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    async def events() -> AsyncIterator[str]:
        nonlocal cursor
        while True:
            batch = manager.events_after(run_id, cursor)
            if batch is None:
                return
            items, run_status = batch
            for item in items:
                cursor = int(item["id"])
                yield (
                    f"id: {cursor}\n"
                    f"event: {item['event']}\n"
                    f"data: {json.dumps(item, separators=(',', ':'))}\n\n"
                )
            if run_status in TERMINAL and not items:
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/v1/runs/{run_id}/cancel", response_model=CancellationResponse, tags=["runs"])
async def cancel_run(run_id: str) -> CancellationResponse:
    result = manager.cancel(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    accepted, run_status = result
    return CancellationResponse(run_id=run_id, accepted=accepted, status=run_status)
