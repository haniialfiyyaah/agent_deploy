"""Environment-backed application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Local LLM Conversation Gateway"
    llm_provider: Literal["mock", "ollama", "openai_compatible"] = "mock"
    database_path: Path = Path("data/gateway.db")
    request_timeout_seconds: float = Field(default=60.0, gt=0)

    system_prompt: str = (
        "You are a concise support assistant. State uncertainty and do not invent "
        "account facts or completed actions."
    )
    context_token_budget: int = Field(default=2048, ge=128)
    context_reserved_output_tokens: int = Field(default=384, ge=32)
    context_recent_messages: int = Field(default=6, ge=2)
    summary_max_characters: int = Field(default=1600, ge=200)
    max_message_characters: int = Field(default=20_000, ge=100)

    mock_stream_delay_seconds: float = Field(default=0.015, ge=0)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:0.5b"
    openai_compatible_base_url: str = "http://127.0.0.1:1234/v1"
    openai_compatible_model: str = "local-model"
    openai_compatible_api_key: str = "lm-studio"

    @property
    def available_input_tokens(self) -> int:
        """Return the input budget after reserving generation capacity."""

        return self.context_token_budget - self.context_reserved_output_tokens


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one settings object for the default application."""

    return Settings()
