from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.mock import MockProvider
from app.settings import Settings


def test_stream_provider_failure_is_an_event_and_error_state(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "failure.db",
        mock_stream_delay_seconds=0,
    )
    provider = MockProvider(fail_after_deltas=2)
    application = create_app(settings=settings, provider=provider)
    headers = {"X-User-ID": "student-01"}

    with TestClient(application) as client:
        thread_id = client.post(
            "/v1/threads",
            headers=headers,
            json={"title": "Failure"},
        ).json()["id"]
        response = client.post(
            f"/v1/threads/{thread_id}/messages/stream",
            headers=headers,
            json={"content": "Trigger a provider failure."},
        )
        detail = client.get(f"/v1/threads/{thread_id}", headers=headers).json()

    assert response.status_code == 200
    assert "event: error" in response.text
    assert response.text.rstrip().endswith("data: {}")
    assert detail["messages"][-1]["status"] == "error"
    assert detail["messages"][-1]["content"]
