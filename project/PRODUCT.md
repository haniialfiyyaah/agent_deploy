# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated and approved: a framework-free browser client served by FastAPI, with plain HTML, CSS, and JavaScript so students can inspect the SSE transport without a frontend build step.

## Users

AI Engineer bootcamp students with basic Python knowledge and limited production-serving experience. They use the client during a four-hour guided lab to create conversation threads, compare non-streaming and streaming delivery, and inspect how context is assembled.

Instructors use the same surface to demonstrate provider failures, cancelled streams, context compaction, and operational metrics.

## Product Purpose

The Local LLM Conversation Gateway turns a local LLM runtime into a stable application-owned API. Success means a student can explain and implement the boundary between a stateless inference runtime and a stateful conversation service.

## Positioning

The gateway normalizes different provider transports into one thread-aware contract while exposing the context, memory, and telemetry decisions that convenience chat applications usually hide.

## Operating Context

The required classroom runtime is Ollama. LM Studio is an approved OpenAI-compatible alternative. A deterministic mock provider keeps setup, automated tests, and demonstrations usable without model downloads or GPU hardware.

The primary workflow is: create or select a thread, send a message, observe streamed tokens, inspect context state, stop a generation when needed, and review service metrics.

## Capabilities and Constraints

- FastAPI owns thread APIs, context construction, summary memory, provider selection, streaming normalization, health checks, and metrics.
- SQLite persists threads and messages for the classroom project; PostgreSQL is discussed as the production migration path.
- Required delivery modes are complete JSON responses and server-sent events.
- Required providers are mock and Ollama; an OpenAI-compatible adapter supports LM Studio.
- The browser client is intentionally small and has no frontend framework or separate build process.
- `X-User-ID` demonstrates an ownership boundary but is not real authentication.
- Long-term vector memory, WebSockets, gRPC implementation, and Module 11 adapter conversion are optional extensions.
- No paid API is required.

## Evidence on Hand

- The course syllabus requires FastAPI, Docker, production monitoring, scaling, and deployment-strategy coverage.
- The approved module scope and runtime choices are recorded in the repository handoff.
- The project ships synthetic conversations and a deterministic mock provider. It has no customer claims, benchmarks, or production traffic evidence.

## Product Principles

1. Make hidden serving decisions inspectable.
2. Keep the provider replaceable and the application contract stable.
3. Preserve complete conversation history while treating model context as a bounded working set.
4. Show failure and cancellation states as first-class behavior.
5. Keep the default lab runnable without paid services or specialized hardware.

## Accessibility & Inclusion

The browser client must work by keyboard, expose visible focus states and text status, avoid color-only state communication, respect reduced-motion preferences, and remain usable on narrow laptop and mobile-width viewports.
