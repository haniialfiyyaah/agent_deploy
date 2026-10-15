from __future__ import annotations

import time

import pytest


pytestmark = pytest.mark.live


def test_live_fastapi_run_reaches_terminal_state(api_client) -> None:
    response = api_client.post(
        "/v1/runs",
        json={
            "message": "What is the current return window? Search policy before answering.",
            "category": "returns",
            "authenticated": False,
            "allow_ticket_creation": False,
            "expected_document_ids": ["KB-RET-001"],
        },
    )
    assert response.status_code == 202
    accepted = response.json()
    inline_snapshot = accepted.get("snapshot")
    if inline_snapshot and inline_snapshot.get("status") in {"completed", "failed", "cancelled"}:
        snapshot = inline_snapshot
    else:
        deadline = time.monotonic() + 150
        snapshot = None
        while time.monotonic() < deadline:
            snapshot_response = api_client.get(accepted["status_url"])
            assert snapshot_response.status_code == 200
            snapshot = snapshot_response.json()
            if snapshot["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.5)
    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert snapshot["result"]["output"]
    assert "API_KEY" not in str(snapshot)
    assert "instructions" not in snapshot["result"]
