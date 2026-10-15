from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.agent import run_customer_service_agent
from src.config import ModelSettings
from src.models import AgentRequest, AgentRun
from src.tools import public_tool_arguments, public_tool_result


LOGGER = logging.getLogger("northstar.service")
TERMINAL = {"completed", "failed", "cancelled"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ManagedRun:
    run_id: str
    request: AgentRequest
    status: str = "queued"
    submitted_at: str = field(default_factory=_timestamp)
    started_at: str | None = None
    completed_at: str | None = None
    result: AgentRun | None = None
    cancel_requested: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)


def public_agent_run(run: AgentRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "conversation_id": run.conversation_id,
        "timestamp": run.timestamp,
        "profile": run.profile,
        "agent_version": run.version,
        "kb_version": run.kb_version,
        "prompt_version": run.prompt_version,
        "output": run.output,
        "tool_calls": [
            {
                "name": call.name,
                "arguments": public_tool_arguments(call.arguments),
                "result": public_tool_result(call.result),
                "status": call.status,
                "authorized": call.authorized,
                "latency_ms": call.latency_ms,
            }
            for call in run.tool_calls
        ],
        "retrievals": [
            {
                "document_ids": item.document_ids,
                "chunk_ids": item.chunk_ids,
                "scores": item.scores,
                "hit_at_3": item.hit_at_3,
            }
            for item in run.retrievals
        ],
        "final_state": run.final_state,
        "latency_ms": run.latency_ms,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "estimated_cost_usd": run.estimated_cost_usd,
        "error": run.error,
    }


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, ManagedRun] = {}
        self._lock = threading.RLock()

    def submit(self, request: AgentRequest, settings: ModelSettings, inline: bool = False) -> ManagedRun:
        managed = ManagedRun(run_id=str(uuid.uuid4()), request=request)
        with self._lock:
            self._runs[managed.run_id] = managed
            self._append_event(managed, "run.queued", {"status": "queued"})
        LOGGER.info(
            json.dumps(
                {
                    "event": "run.submitted",
                    "run_id": managed.run_id,
                    "category": request.category,
                    "inline": inline,
                }
            )
        )
        # Vercel freezes the function after the response, so the model call has to
        # finish before POST returns. Local and Render keep the background thread.
        if inline:
            self._execute(managed.run_id, settings)
            return managed
        thread = threading.Thread(
            target=self._execute,
            args=(managed.run_id, settings),
            name=f"northstar-{managed.run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return managed

    def _append_event(self, managed: ManagedRun, event: str, data: dict[str, Any]) -> None:
        managed.events.append(
            {
                "id": len(managed.events) + 1,
                "event": event,
                "timestamp": _timestamp(),
                "data": data,
            }
        )

    def _execute(self, run_id: str, settings: ModelSettings) -> None:
        with self._lock:
            managed = self._runs[run_id]
            if managed.cancel_requested:
                managed.status = "cancelled"
                managed.completed_at = _timestamp()
                self._append_event(managed, "run.cancelled", {"status": managed.status})
                return
            managed.status = "running"
            managed.started_at = _timestamp()
            self._append_event(managed, "run.started", {"status": managed.status, "model": settings.agent_model})

        def emit(event: str, data: dict[str, Any]) -> None:
            with self._lock:
                self._append_event(managed, event, data)

        def cancelled() -> bool:
            with self._lock:
                return managed.cancel_requested

        try:
            result = run_customer_service_agent(
                managed.request,
                settings=settings,
                run_id=run_id,
                event_sink=emit,
                cancel_check=cancelled,
            )
        except Exception:
            with self._lock:
                managed.status = "failed"
                managed.completed_at = _timestamp()
                self._append_event(
                    managed,
                    "run.failed",
                    {"status": "failed", "error": "service_execution_failed"},
                )
            LOGGER.error(
                json.dumps(
                    {
                        "event": "run.failed",
                        "run_id": run_id,
                        "status": "failed",
                        "error": "service_execution_failed",
                    }
                )
            )
            return
        with self._lock:
            managed.result = result
            managed.completed_at = _timestamp()
            if result.error == "cancelled":
                managed.status = "cancelled"
                event = "run.cancelled"
            elif result.error:
                managed.status = "failed"
                event = "run.failed"
            else:
                managed.status = "completed"
                event = "run.completed"
            self._append_event(
                managed,
                event,
                {
                    "status": managed.status,
                    "latency_ms": result.latency_ms,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "estimated_cost_usd": result.estimated_cost_usd,
                },
            )
        LOGGER.info(json.dumps({"event": event, "run_id": run_id, "status": managed.status, "latency_ms": result.latency_ms}))

    def get(self, run_id: str) -> ManagedRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def snapshot(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            managed = self._runs.get(run_id)
            if managed is None:
                return None
            return {
                "run_id": managed.run_id,
                "status": managed.status,
                "submitted_at": managed.submitted_at,
                "started_at": managed.started_at,
                "completed_at": managed.completed_at,
                "result": public_agent_run(managed.result) if managed.result else None,
            }

    def events_after(self, run_id: str, event_id: int) -> tuple[list[dict[str, Any]], str] | None:
        with self._lock:
            managed = self._runs.get(run_id)
            if managed is None:
                return None
            return [event for event in managed.events if event["id"] > event_id], managed.status

    def cancel(self, run_id: str) -> tuple[bool, str] | None:
        with self._lock:
            managed = self._runs.get(run_id)
            if managed is None:
                return None
            if managed.status in TERMINAL:
                return False, managed.status
            managed.cancel_requested = True
            self._append_event(managed, "run.cancellation_requested", {"status": managed.status})
            return True, managed.status
