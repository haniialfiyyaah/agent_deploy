from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


AgentVersion = Literal["baseline", "candidate"]
KnowledgeBaseVersion = Literal["healthy", "stale"]


@dataclass(frozen=True)
class AgentRequest:
    message: str
    customer_id: str | None = None
    authenticated: bool = False
    conversation_id: str | None = None
    category: str = "unknown"
    expected_document_ids: list[str] = field(default_factory=list)
    allow_ticket_creation: bool = False


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    status: str
    latency_ms: float
    authorized: bool = True


@dataclass(frozen=True)
class RetrievalRecord:
    query: str
    kb_version: KnowledgeBaseVersion
    chunk_ids: list[str]
    document_ids: list[str]
    scores: list[float]
    expected_document_ids: list[str]

    @property
    def hit_at_3(self) -> float:
        if not self.expected_document_ids:
            return 1.0
        return float(bool(set(self.document_ids[:3]) & set(self.expected_document_ids)))


@dataclass(frozen=True)
class TraceSpan:
    span_id: str
    run_id: str
    parent_span_id: str | None
    span_type: str
    name: str
    status: str
    latency_ms: float
    input_summary: dict[str, Any]
    output_summary: dict[str, Any]


@dataclass(frozen=True)
class AgentRun:
    run_id: str
    conversation_id: str
    timestamp: str
    profile: str
    version: AgentVersion
    kb_version: KnowledgeBaseVersion
    prompt_version: str
    request: AgentRequest
    output: str
    tool_calls: list[ToolCallRecord]
    retrievals: list[RetrievalRecord]
    final_state: dict[str, Any]
    spans: list[TraceSpan]
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
