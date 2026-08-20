from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
APP_DB = DATA_DIR / "customer_service.db"
TELEMETRY_DB = DATA_DIR / "telemetry.db"


@dataclass(frozen=True)
class ModelSettings:
    api_key: str
    agent_model: str
    base_url: str | None = None


def load_model_settings() -> ModelSettings:
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path, override=False)

    api_key = os.getenv("API_KEY")
    agent_model = os.getenv("AGENT_MODEL")
    missing = [
        name
        for name, value in (("API_KEY", api_key), ("AGENT_MODEL", agent_model))
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required model configuration: " + ", ".join(missing) + ". "
            "Copy .env.example to .env and add the instructor-provided values."
        )
    return ModelSettings(
        api_key=api_key,
        agent_model=agent_model,
        base_url=os.getenv("API_BASE_URL"),
    )


def app_version() -> str:
    return os.getenv("APP_VERSION", "module12-v2")


def readiness_forced_down() -> bool:
    return os.getenv("FORCE_READINESS_FAILURE", "0").casefold() in {"1", "true", "yes"}
