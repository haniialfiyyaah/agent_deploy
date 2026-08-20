from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.config import ModelSettings, load_model_settings
from src.setup_lab import setup


@pytest.fixture(scope="session", autouse=True)
def initialized_live_lab() -> None:
    # Deliberately fail instead of skip: this project has no mock runtime mode.
    load_model_settings()
    setup(reset=True)


@pytest.fixture(scope="session")
def live_settings() -> ModelSettings:
    return load_model_settings()


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
