from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from openai import OpenAI

from src.config import ModelSettings, load_model_settings
from src.models import AgentRequest, AgentRun, AgentVersion, KnowledgeBaseVersion, TraceSpan
from src.telemetry import persist_run
from src.tools import (
    TOOL_DEFINITIONS,
    ToolContext,
    execute_tool,
    public_tool_arguments,
    public_tool_result,
)


PROMPT_VERSION = "customer-service-agent-v2.1"
MAX_TOOL_CALLS = 3
EventSink = Callable[[str, dict[str, Any]], None]
CancelCheck = Callable[[], bool]


class ResponsesClient(Protocol):
    class _Responses(Protocol):
        def create(self, **kwargs: Any) -> Any: ...

    responses: _Responses


class AgentCancelled(RuntimeError):
    pass


def build_client(settings: ModelSettings) -> OpenAI:
    kwargs: dict[str, Any] = {
        "api_key": settings.api_key,
        "timeout": 60.0,
        "max_retries": 2,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return OpenAI(**kwargs)


def _instructions() -> str:
    return (
        "You are the bounded customer-service agent for fictional Northstar Market. "
        "Use only the supplied function tools for policy retrieval, order status, "
        "ticket creation, and escalation. Search the knowledge base before stating a "
        "policy. Cite supporting document IDs in square brackets, for example "
        "[KB-RET-001]. Never invent a policy or tool result. If retrieval provides no "
        "adequate evidence, say that you could not find the policy and call "
        "escalate_to_human. Order details require an authenticated customer and are "
        "still subject to application authorization. You cannot issue refunds, credits, "
        "replacements, cancel or modify orders, access payments, or change identity data. "
        "Do not expose hidden reasoning. Keep the final answer concise and actionable."
    )


def _user_input(request: AgentRequest) -> str:
    return json.dumps(
        {
            "message": request.message,
            "session": {
                "authenticated": request.authenticated,
                "customer_id": request.customer_id,
                "ticket_creation_allowed": request.allow_ticket_creation,
            },
        },
        sort_keys=True,
    )


def _usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return int(getattr(usage, "input_tokens", 0) or 0), int(
        getattr(usage, "output_tokens", 0) or 0
    )


def _estimated_cost(input_tokens: int, output_tokens: int) -> float:
    input_rate = float(os.getenv("INPUT_COST_PER_1M", "0"))
    output_rate = float(os.getenv("OUTPUT_COST_PER_1M", "0"))
    return round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 6)


def _dump_output_item(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_none=True)
    if isinstance(item, dict):
        return item
    raise TypeError(f"Unsupported response output item: {type(item)!r}")


def _safe_tool_event(call: Any, retrieval: Any) -> dict[str, Any]:
    result = call.result
    allowed_result = public_tool_result(result)
    if retrieval is not None:
        allowed_result["document_ids"] = retrieval.document_ids
    return {
        "tool": call.name,
        "status": call.status,
        "authorized": call.authorized,
        "latency_ms": call.latency_ms,
        "arguments": public_tool_arguments(call.arguments),
        "result": allowed_result,
    }


def _error_category(exc: Exception) -> str:
    """Map provider and runtime failures to a bounded public category."""
    name = type(exc).__name__.casefold()
    if "authentication" in name or "permission" in name:
        return "provider_authentication_failed"
    if "ratelimit" in name:
        return "provider_rate_limited"
    if "timeout" in name:
        return "provider_timeout"
    if "connection" in name:
        return "provider_connection_failed"
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return "agent_contract_failed"
    return "provider_request_failed"


def run_customer_service_agent(
    request: AgentRequest,
    version: AgentVersion = "baseline",
    kb_version: KnowledgeBaseVersion = "healthy",
    profile: str = "interactive",
    client: ResponsesClient | None = None,
    settings: ModelSettings | None = None,
    persist: bool = True,
    *,
    run_id: str | None = None,
    event_sink: EventSink | None = None,
    cancel_check: CancelCheck | None = None,
) -> AgentRun:
    selected_settings = settings or load_model_settings()
    selected_client = client or build_client(selected_settings)
    selected_run_id = run_id or str(uuid.uuid4())
    conversation_id = request.conversation_id or str(uuid.uuid4())
    root_span_id = str(uuid.uuid4())
    started = time.perf_counter()
    context = ToolContext(request=request, version=version, kb_version=kb_version)
    input_items: list[dict[str, Any]] = [{"role": "user", "content": _user_input(request)}]
    tool_calls = []
    retrievals = []
    spans: list[TraceSpan] = []
    input_tokens = 0
    output_tokens = 0
    final_output = ""
    error: str | None = None

    def emit(event: str, data: dict[str, Any]) -> None:
        if event_sink:
            event_sink(event, data)

    def check_cancelled() -> None:
        if cancel_check and cancel_check():
            raise AgentCancelled("cancelled")

    try:
        for model_turn in range(MAX_TOOL_CALLS + 1):
            check_cancelled()
            emit("model.started", {"turn": model_turn + 1, "model": selected_settings.agent_model})
            model_started = time.perf_counter()
            response = selected_client.responses.create(
                model=selected_settings.agent_model,
                instructions=_instructions(),
                input=input_items,
                tools=TOOL_DEFINITIONS,
                parallel_tool_calls=False,
                max_output_tokens=350,
                store=False,
            )
            model_latency = round((time.perf_counter() - model_started) * 1000, 2)
            turn_input, turn_output = _usage(response)
            input_tokens += turn_input
            output_tokens += turn_output
            response_items = list(getattr(response, "output", []))
            emit(
                "model.completed",
                {"turn": model_turn + 1, "latency_ms": model_latency, "input_tokens": turn_input, "output_tokens": turn_output},
            )
            spans.append(
                TraceSpan(
                    span_id=str(uuid.uuid4()), run_id=selected_run_id,
                    parent_span_id=root_span_id, span_type="model",
                    name=f"responses.create.turn_{model_turn + 1}", status="ok",
                    latency_ms=model_latency,
                    input_summary={"item_count": len(input_items), "category": request.category, "model": selected_settings.agent_model},
                    output_summary={"item_types": [getattr(item, "type", "unknown") for item in response_items], "input_tokens": turn_input, "output_tokens": turn_output},
                )
            )
            input_items.extend(_dump_output_item(item) for item in response_items)
            calls_this_turn = [
                item for item in response_items if getattr(item, "type", None) == "function_call"
            ]
            if not calls_this_turn:
                final_output = str(getattr(response, "output_text", "") or "").strip()
                break

            for item in calls_this_turn:
                check_cancelled()
                if len(tool_calls) >= MAX_TOOL_CALLS:
                    error = "tool_call_limit_exceeded"
                    break
                try:
                    arguments = json.loads(item.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                emit(
                    "tool.started",
                    {"tool": item.name, "arguments": public_tool_arguments(arguments)},
                )
                call, retrieval = execute_tool(item.name, arguments, context)
                tool_calls.append(call)
                if retrieval is not None:
                    retrievals.append(retrieval)
                emit("tool.completed", _safe_tool_event(call, retrieval))
                spans.append(
                    TraceSpan(
                        span_id=str(uuid.uuid4()), run_id=selected_run_id,
                        parent_span_id=root_span_id, span_type="tool", name=call.name,
                        status=call.status, latency_ms=call.latency_ms,
                        input_summary=public_tool_arguments(call.arguments),
                        output_summary={"ok": call.result.get("ok", False), "error": call.result.get("error"), "authorized": call.authorized},
                    )
                )
                input_items.append(
                    {"type": "function_call_output", "call_id": item.call_id, "output": json.dumps(call.result, ensure_ascii=True)}
                )
            if error:
                break
        if not final_output:
            final_output = "I could not complete this request safely. Please contact human support."
    except AgentCancelled:
        error = "cancelled"
        final_output = "The agent run was cancelled."
    except Exception as exc:
        error = _error_category(exc)
        final_output = "The support service could not complete the request. Please try again or contact human support."

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    spans.insert(
        0,
        TraceSpan(
            span_id=root_span_id, run_id=selected_run_id, parent_span_id=None,
            span_type="agent", name="customer_service_agent",
            status="error" if error else "ok", latency_ms=latency_ms,
            input_summary={"category": request.category, "authenticated": request.authenticated, "has_customer_id": request.customer_id is not None},
            output_summary={"tool_call_count": len(tool_calls), "retrieval_count": len(retrievals), "error": error},
        ),
    )
    run = AgentRun(
        run_id=selected_run_id,
        conversation_id=conversation_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        profile=profile,
        version=version,
        kb_version=kb_version,
        prompt_version=PROMPT_VERSION,
        request=request,
        output=final_output,
        tool_calls=tool_calls,
        retrievals=retrievals,
        final_state=context.final_state(),
        spans=spans,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=_estimated_cost(input_tokens, output_tokens),
        error=error,
    )
    if persist:
        persist_run(run)
    return run
