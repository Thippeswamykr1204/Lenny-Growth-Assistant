"""
validate_config() is the single function both main.py's startup (fail
fast) and health.py's /api/health (surface "misconfigured") call — these
tests cover the decision logic itself, independent of either call site.
No DB, no live provider.
"""
from app.core.config import Settings, validate_config
from app.core.errors import ConfigurationError


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        default_llm_provider="ollama",
        groq_api_key=None,
    )
    base.update(overrides)
    return Settings(**base)


def test_ollama_default_never_requires_groq_key():
    # Explicit regression guard: GROQ_API_KEY must stay genuinely
    # optional when it isn't actually needed, per .env.example and the
    # hard constraint against regressing that.
    settings = _settings(default_llm_provider="ollama", groq_api_key=None)
    assert validate_config(settings) == []


def test_groq_default_without_key_is_a_config_issue():
    settings = _settings(default_llm_provider="groq", groq_api_key=None)
    issues = validate_config(settings)
    assert len(issues) == 1
    assert isinstance(issues[0], ConfigurationError)
    assert "GROQ_API_KEY" in issues[0].detail


def test_groq_default_with_key_present_is_fine():
    settings = _settings(default_llm_provider="groq", groq_api_key="sk-ant-fake")
    assert validate_config(settings) == []


def test_unknown_default_provider_is_a_config_issue():
    settings = _settings(default_llm_provider="totally-not-a-provider")
    issues = validate_config(settings)
    assert len(issues) == 1
    assert "totally-not-a-provider" in issues[0].detail


def test_provider_name_is_case_insensitive():
    settings = _settings(default_llm_provider="Groq", groq_api_key="sk-ant-fake")
    assert validate_config(settings) == []
