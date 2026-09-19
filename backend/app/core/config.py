"""
Centralized configuration. Every environment variable the backend reads
should be declared here, not fetched ad-hoc with os.getenv() scattered
through the codebase — that discipline is what keeps .env.example
trustworthy as the single source of truth for "what this app needs."

Tier 1 scope: only the variables needed to boot and health-check.
Provider API keys, chunking params, retrieval thresholds, etc. are
declared here as placeholders where the shape is already known from
architecture.md, but are NOT consumed by any logic yet — that's Tier 2+.
"""
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core app ---
    app_env: str = "development"
    log_level: str = "INFO"

    # --- Database (required) ---
    database_url: str

    # --- Provider routing (locked decision: env-var default, never model-decided) ---
    default_llm_provider: str = "ollama"

    # --- Ollama (only meaningful if the local-ai profile is running) ---
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2:3b"

    # --- Groq (OpenAI-compatible cloud provider, free tier) ---
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    
    # --- Frontend-facing (consumed by Next.js, listed here for completeness) ---
    next_public_api_url: str = "http://localhost:8000"

    # --- Ingestion (Tier 2) ---
    # Embedding model choice locked at start of Tier 2: local sentence-transformers,
    # 384-dim, matches transcript_chunks.embedding as already migrated in 001_init.sql
    # (no migration change needed). Chosen over an Ollama embedding model because it
    # needs no local-ai profile running during ingestion and stays fully offline.
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    chunk_target_tokens: int = 650
    chunk_overlap_tokens: int = 100
    transcripts_source_repo: str = "https://github.com/ChatPRD/lennys-podcast-transcripts"
    transcripts_dir: str = "data/transcripts"

    # --- Retrieval / confidence gating (Tier 3) ---
    # Defaults per architecture.md's best-guess thresholds, explicitly flagged
    # there as pending real eval — configurable here, not hardcoded in
    # retriever.py, so they can be tuned without a code change.
    retrieval_top_k: int = 5
    similarity_threshold_high: float = 0.75
    similarity_threshold_moderate: float = 0.65

    # Kept as the fallback/default both per-provider timeouts below inherit
    # from when not overridden individually — existing callers/tests that
    # only know about this one field keep working unchanged.
    provider_timeout_seconds: float = 30.0

    # --- Ship 30 for 30 skill (Tier 4) ---
    # Deterministic validator band, not a hardcoded literal in the skill
    # module, so it can be tuned without a code change (same rationale as
    # the retrieval thresholds above).
    ship30_min_words: int = 1100
    ship30_max_words: int = 1400

    # --- Resilience: explicit per-dependency timeouts (Tier 5) ---
    # Split out from the single provider_timeout_seconds so Ollama (local,
    # usually fast but can hang if the model is still loading) and
    # Anthropic (network-bound, subject to provider-side load) can be tuned
    # independently without one setting fighting two different failure
    # profiles. Both default to provider_timeout_seconds's value so nothing
    # changes for anyone who hasn't touched these new variables.
    ollama_timeout_seconds: float | None = None
    groq_timeout_seconds: float | None = None

    @field_validator("ollama_timeout_seconds", "groq_timeout_seconds", mode="before")
    @classmethod
    def _blank_env_string_means_unset(cls, value):
        # Docker Compose's ${VAR:-} syntax always sets the env var, defaulting
        # to an empty string rather than leaving it truly unset. Pydantic treats
        # "" as an invalid float rather than as "use the default (None)", so we
        # coerce it here before validation reaches the float parser.
        if value == "":
            return None
        return value
    # DB pool acquire timeout: how long a request waits for a free
    # connection before giving up, distinct from the query itself timing
    # out. Short by design — if the pool is exhausted or the DB is down,
    # callers should fail fast into DatabaseUnavailableError rather than
    # queuing requests indefinitely behind a dead dependency.
    db_pool_timeout_seconds: float = 5.0

    # --- Resilience: prompt size validation (Tier 5) ---
    # Empty prompts were already rejected (chat.py's 422 on blank message);
    # nothing previously bounded the upper end, so a pathological payload
    # could reach the provider (and its token/cost limits) unvalidated.
    # 8000 chars is a generous few-thousand-word ceiling for a chat turn.
    max_prompt_chars: int = 8000

    def resolved_ollama_timeout(self) -> float:
        return self.ollama_timeout_seconds if self.ollama_timeout_seconds is not None else self.provider_timeout_seconds


    def resolved_groq_timeout(self) -> float:
        return self.groq_timeout_seconds if self.groq_timeout_seconds is not None else self.provider_timeout_seconds
    
@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_config(settings: Settings) -> list["ConfigurationError"]:
    """Single source of truth for "is this config minimally usable",
    called from both main.py's startup (fail fast) and health.py's
    /api/health (surface "misconfigured" as a distinct runtime state) —
    one function, two call sites, so the two can never drift apart.

    Only checks what's required for the app to be minimally useful, per
    Tier 5 scope: does NOT require GROQ_API_KEY when
    default_llm_provider=ollama (that stays genuinely optional, matching
    .env.example) — only when it's actually the configured default and
    would be silently unusable on the first real chat request otherwise.
    """
    from app.core.errors import ConfigurationError  # local import: avoid a config<->errors import cycle

    issues: list[ConfigurationError] = []

    provider = settings.default_llm_provider.lower()
    if provider == "groq" and not settings.groq_api_key:
        issues.append(
            ConfigurationError(
                message="The server is misconfigured: no cloud provider credentials.",
                detail=(
                    "DEFAULT_LLM_PROVIDER=groq but GROQ_API_KEY is not set. "
                    "Set GROQ_API_KEY, or set DEFAULT_LLM_PROVIDER=ollama."
                ),
            )
        )
    elif provider not in ("ollama", "groq"):
        issues.append(
            ConfigurationError(
                message="The server is misconfigured: unknown default provider.",
                detail=f"DEFAULT_LLM_PROVIDER={settings.default_llm_provider!r} is not 'ollama' or 'groq'.",
            )
        )

    return issues