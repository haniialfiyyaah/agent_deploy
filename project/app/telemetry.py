"""Prometheus metrics with one registry per application instance."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class Telemetry:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "llm_gateway_requests_total",
            "Completed gateway inference requests.",
            ("mode", "provider", "status"),
            registry=self.registry,
        )
        self.request_duration = Histogram(
            "llm_gateway_request_duration_seconds",
            "End-to-end inference request duration.",
            ("mode", "provider"),
            registry=self.registry,
        )
        self.time_to_first_token = Histogram(
            "llm_gateway_time_to_first_token_seconds",
            "Time from stream start to first output delta.",
            ("provider",),
            registry=self.registry,
        )
        self.active_streams = Gauge(
            "llm_gateway_active_streams",
            "Currently active downstream streams.",
            ("provider",),
            registry=self.registry,
        )
        self.cancelled_streams = Counter(
            "llm_gateway_cancelled_streams_total",
            "Streams cancelled before completion.",
            ("provider",),
            registry=self.registry,
        )
        self.context_compactions = Counter(
            "llm_gateway_context_compactions_total",
            "Context summary compactions.",
            ("provider",),
            registry=self.registry,
        )
        self.tokens = Counter(
            "llm_gateway_tokens_total",
            "Input and output tokens reported or estimated.",
            ("direction", "provider"),
            registry=self.registry,
        )
        self.provider_ready = Gauge(
            "llm_gateway_provider_ready",
            "Whether the configured provider reports ready.",
            ("provider", "model"),
            registry=self.registry,
        )
