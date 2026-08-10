# Local LLM Conversation Gateway

A teaching-grade FastAPI service that owns conversation threads, bounded context, provider adaptation, SSE delivery, and Prometheus metrics around a local LLM runtime.

## Quick Start: No Model Download

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest -q
LLM_PROVIDER=mock uvicorn app.main:app --reload
```

Open:

- Client: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Readiness: `http://127.0.0.1:8000/health/ready`
- Metrics: `http://127.0.0.1:8000/metrics`

The browser uses `student-01` as its classroom owner ID. API clients must send `X-User-ID`; this is an ownership exercise, not authentication.

## Ollama

Install Ollama using its official documentation, pull an instructor-approved small model, and configure `.env`:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:0.5b
```

```bash
ollama pull qwen2.5:0.5b
ollama list
uvicorn app.main:app --reload
```

The model tag is an example, not a permanent recommendation. Recheck size, license, chat behavior, and hardware compatibility before class.

## LM Studio

Load a model, start the local server, and configure:

```dotenv
LLM_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_BASE_URL=http://127.0.0.1:1234/v1
OPENAI_COMPATIBLE_MODEL=<loaded-model-identifier>
OPENAI_COMPATIBLE_API_KEY=lm-studio
```

The adapter uses the OpenAI-compatible chat-completions contract. It does not depend on LM Studio's provider-owned stateful chat API.

## API Contract

```text
POST   /v1/threads
GET    /v1/threads
GET    /v1/threads/{thread_id}
DELETE /v1/threads/{thread_id}
POST   /v1/threads/{thread_id}/messages
POST   /v1/threads/{thread_id}/messages/stream
GET    /health/live
GET    /health/ready
GET    /metrics
```

The stream endpoint emits:

```text
message.start
context.compacted   # only when triggered
message.delta       # repeated
message.completed
usage
done
```

Provider failures after streaming starts emit `error` followed by `done`. The assistant message is stored with `error`, not `completed`.

Only one generation may run per thread. An overlapping request receives `409`; this in-process guard must become distributed coordination before multiple gateway replicas serve the same thread.

## Docker

Mock provider:

```bash
docker compose up --build gateway
```

Ollama in Compose:

```bash
docker compose --profile ollama up -d ollama
docker compose exec ollama ollama pull qwen2.5:0.5b
LLM_PROVIDER=ollama docker compose --profile ollama up --build gateway
```

Prometheus:

```bash
docker compose --profile monitoring up -d prometheus
```

Open `http://127.0.0.1:9090` and query `llm_gateway_requests_total`.

The Compose file uses `latest` tags to keep classroom setup approachable. Pin image digests and verify them in a production release pipeline.

## Configuration Notes

- `CONTEXT_TOKEN_BUDGET` includes input and reserved output.
- `CONTEXT_RESERVED_OUTPUT_TOKENS` is subtracted before context selection.
- `CONTEXT_RECENT_MESSAGES` counts individual messages, not user-assistant pairs.
- The character-based token estimate is approximate.
- `DATABASE_PATH` must be writable by the service user.
- Do not put real secrets into `.env.example`, source control, prompts, or metrics.

## Educational Boundaries

This project deliberately uses synchronous standard-library SQLite access to keep persistence visible. Before horizontal production scaling, move to a shared database and add authentication, migrations, limits, idempotency, tracing, managed secrets, retention controls, and a tested inference-capacity plan.
