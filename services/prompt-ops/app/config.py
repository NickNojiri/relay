from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgres://relay:relay@localhost:5432/relay"
    redis_url: str = "redis://localhost:6379"
    ollama_base_url: str = "http://localhost:11434"
    relay_default_provider: str = "ollama"
    relay_default_model: str = "llama3.2"
    relay_db_enabled: bool = False
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    # Any OpenAI-compatible server (vLLM, LM Studio, Ollama's /v1) can stand in for OpenAI.
    openai_base_url: str = "https://api.openai.com"
    # Per-provider HTTP timeouts in seconds, e.g. {"ollama": {"connect": 2, "read": 60}}.
    # Providers not listed use providers.DEFAULT_TIMEOUTS.
    relay_timeouts: dict[str, dict[str, float]] = {}
    # Routes tried after a prompt version's own fallbacks,
    # e.g. [{"provider": "anthropic", "model": "claude-haiku-4-5"}].
    relay_fallbacks: list[dict[str, str]] = []
    # Gateway hardening (both opt-in; see app/security.py)
    relay_api_keys: str = ""
    relay_rate_limit_per_minute: int = 0
    # Observability (opt-in; see app/telemetry_otel.py). Exporter is configured
    # via the standard OTEL_EXPORTER_OTLP_ENDPOINT env var.
    relay_otel_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
