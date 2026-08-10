from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.mock import MockProvider
from app.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        llm_provider="mock",
        database_path=tmp_path / "gateway.db",
        mock_stream_delay_seconds=0,
        context_token_budget=512,
        context_reserved_output_tokens=96,
        context_recent_messages=4,
        summary_max_characters=600,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    application = create_app(settings=settings, provider=MockProvider())
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def owner_headers() -> dict[str, str]:
    return {"X-User-ID": "student-01"}
