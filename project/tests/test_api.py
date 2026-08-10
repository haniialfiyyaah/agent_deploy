from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient


def create_thread(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/v1/threads",
        headers=headers,
        json={"title": "Serving lab"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_health_and_metrics(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "alive"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["provider"] == "mock"
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "llm_gateway_requests_total" in metrics.text


def test_thread_owner_isolation(
    client: TestClient,
    owner_headers: dict[str, str],
) -> None:
    thread_id = create_thread(client, owner_headers)

    own_response = client.get(f"/v1/threads/{thread_id}", headers=owner_headers)
    other_response = client.get(
        f"/v1/threads/{thread_id}",
        headers={"X-User-ID": "student-02"},
    )

    assert own_response.status_code == 200
    assert other_response.status_code == 404


def test_complete_message_persists_ordered_records(
    client: TestClient,
    owner_headers: dict[str, str],
) -> None:
    thread_id = create_thread(client, owner_headers)
    response = client.post(
        f"/v1/threads/{thread_id}/messages",
        headers=owner_headers,
        json={"content": "Explain readiness."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_message"]["content"].startswith("Mock response:")
    assert payload["context"]["compacted"] is False

    detail = client.get(f"/v1/threads/{thread_id}", headers=owner_headers).json()
    assert [message["position"] for message in detail["messages"]] == [0, 1]
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert all(message["status"] == "completed" for message in detail["messages"])


def test_stream_has_stable_event_order(
    client: TestClient,
    owner_headers: dict[str, str],
) -> None:
    thread_id = create_thread(client, owner_headers)
    response = client.post(
        f"/v1/threads/{thread_id}/messages/stream",
        headers=owner_headers,
        json={"content": "Name two useful metrics."},
    )

    assert response.status_code == 200
    events = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]
    assert events[0] == "message.start"
    assert "message.delta" in events
    assert events[-3:] == ["message.completed", "usage", "done"]

    detail = client.get(f"/v1/threads/{thread_id}", headers=owner_headers).json()
    assert detail["messages"][-1]["status"] == "completed"


def test_rejects_blank_content(
    client: TestClient,
    owner_headers: dict[str, str],
) -> None:
    thread_id = create_thread(client, owner_headers)
    response = client.post(
        f"/v1/threads/{thread_id}/messages",
        headers=owner_headers,
        json={"content": "   "},
    )
    assert response.status_code == 422


def test_delete_thread_cascades_messages(
    client: TestClient,
    owner_headers: dict[str, str],
) -> None:
    thread_id = create_thread(client, owner_headers)
    client.post(
        f"/v1/threads/{thread_id}/messages",
        headers=owner_headers,
        json={"content": "Persist this."},
    )

    deleted = client.delete(f"/v1/threads/{thread_id}", headers=owner_headers)
    missing = client.get(f"/v1/threads/{thread_id}", headers=owner_headers)

    assert deleted.status_code == 204
    assert missing.status_code == 404


def test_thread_rejects_overlapping_generations(settings) -> None:
    from app.main import create_app
    from app.providers.mock import MockProvider

    application = create_app(
        settings=settings,
        provider=MockProvider(delay_seconds=0.03),
    )
    headers = {"X-User-ID": "student-01"}
    first_status: list[int] = []

    with TestClient(application) as client:
        thread_id = create_thread(client, headers)

        def send_first() -> None:
            response = client.post(
                f"/v1/threads/{thread_id}/messages/stream",
                headers=headers,
                json={"content": "Generate slowly enough to overlap."},
            )
            first_status.append(response.status_code)

        worker = threading.Thread(target=send_first)
        worker.start()
        time.sleep(0.08)
        second = client.post(
            f"/v1/threads/{thread_id}/messages",
            headers=headers,
            json={"content": "This request should be rejected."},
        )
        delete_during_generation = client.delete(
            f"/v1/threads/{thread_id}",
            headers=headers,
        )
        worker.join()

    assert first_status == [200]
    assert second.status_code == 409
    assert delete_during_generation.status_code == 409


def test_configured_message_limit_is_enforced(tmp_path) -> None:
    from app.main import create_app
    from app.providers.mock import MockProvider
    from app.settings import Settings

    settings = Settings(
        database_path=tmp_path / "limit.db",
        max_message_characters=100,
    )
    headers = {"X-User-ID": "student-01"}
    application = create_app(settings=settings, provider=MockProvider())

    with TestClient(application) as client:
        thread_id = create_thread(client, headers)
        response = client.post(
            f"/v1/threads/{thread_id}/messages",
            headers=headers,
            json={"content": "x" * 101},
        )

    assert response.status_code == 413
