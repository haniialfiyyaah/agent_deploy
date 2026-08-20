from __future__ import annotations

from pathlib import Path

from src.config import APP_DB, TELEMETRY_DB
from src.db import connect, json_text
from src.models import AgentRun
from src.tools import public_tool_arguments


def _segment(customer_id: str | None, app_db: Path = APP_DB) -> str:
    if customer_id is None:
        return "anonymous"
    with connect(app_db) as connection:
        row = connection.execute(
            "SELECT segment FROM customers WHERE customer_id = ?", (customer_id,)
        ).fetchone()
    return "unknown" if row is None else str(row["segment"])


def persist_run(run: AgentRun, telemetry_db: Path = TELEMETRY_DB) -> None:
    outcome = (
        "error" if run.error else
        "escalated" if run.final_state.get("escalated") else
        "ticket_created" if run.final_state.get("ticket_created") else
        "answered"
    )
    with connect(telemetry_db) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO agent_runs(
            run_id, conversation_id, timestamp, profile, agent_version,
            kb_version, prompt_version, category, customer_segment, outcome,
            output, latency_ms, input_tokens, output_tokens, estimated_cost_usd, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.run_id, run.conversation_id, run.timestamp, run.profile, run.version,
                run.kb_version, run.prompt_version, run.request.category,
                _segment(run.request.customer_id), outcome, run.output, run.latency_ms,
                run.input_tokens, run.output_tokens, run.estimated_cost_usd, run.error,
            ),
        )
        connection.executemany(
            """INSERT OR REPLACE INTO trace_spans(
            span_id, run_id, parent_span_id, span_type, name, status,
            latency_ms, input_summary, output_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    span.span_id, span.run_id, span.parent_span_id, span.span_type,
                    span.name, span.status, span.latency_ms,
                    json_text(span.input_summary), json_text(span.output_summary),
                )
                for span in run.spans
            ],
        )
        connection.executemany(
            """INSERT INTO retrieval_events(
            run_id, query, kb_version, chunk_ids, document_ids, scores,
            expected_document_ids, hit_at_3
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    run.run_id, "[REDACTED_QUERY]", item.kb_version, json_text(item.chunk_ids),
                    json_text(item.document_ids), json_text(item.scores),
                    json_text(item.expected_document_ids), item.hit_at_3,
                )
                for item in run.retrievals
            ],
        )
        connection.executemany(
            """INSERT INTO tool_events(
            run_id, tool_name, sanitized_arguments, status, authorized, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    run.run_id, item.name, json_text(public_tool_arguments(item.arguments)), item.status,
                    int(item.authorized), item.latency_ms,
                )
                for item in run.tool_calls
            ],
        )
