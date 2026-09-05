"""No DB, no live provider call — just verifies the factory returns the
right class for config default vs. explicit override, and rejects unknown
provider names. Confirms selection is app logic, never model-decided."""
import pytest

from app.core.config import Settings
from app.providers.cloud_provider import AnthropicProvider
from app.providers.factory import UnknownProviderError, get_provider
from app.providers.ollama_provider import OllamaProvider


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        default_llm_provider="ollama",
        ollama_base_url="http://ollama:11434",
        ollama_model="llama3.2:3b",
        anthropic_api_key=None,
        anthropic_model="claude-3-5-sonnet-20241022",
        provider_timeout_seconds=30.0,
    )
    base.update(overrides)
    return Settings(**base)


def test_default_provider_from_config():
    settings = _settings(default_llm_provider="ollama")
    provider = get_provider(settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"


def test_per_request_override_wins_over_config_default():
    settings = _settings(default_llm_provider="ollama")
    provider = get_provider(settings, override="anthropic")
    assert isinstance(provider, AnthropicProvider)
    assert provider.name == "anthropic"


def test_unknown_provider_raises():
    settings = _settings(default_llm_provider="ollama")
    with pytest.raises(UnknownProviderError):
        get_provider(settings, override="totally-not-a-provider")