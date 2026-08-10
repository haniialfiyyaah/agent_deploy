"""Provider factory for local and deterministic inference backends."""

from app.providers.base import LLMProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.settings import Settings


def create_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockProvider(delay_seconds=settings.mock_stream_delay_seconds)
    if settings.llm_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
    return OpenAICompatibleProvider(
        base_url=settings.openai_compatible_base_url,
        model=settings.openai_compatible_model,
        api_key=settings.openai_compatible_api_key,
        timeout_seconds=settings.request_timeout_seconds,
    )


__all__ = ["LLMProvider", "create_provider"]
