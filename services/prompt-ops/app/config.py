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
    # Gateway hardening (both opt-in; see app/security.py)
    relay_api_keys: str = ""
    relay_rate_limit_per_minute: int = 0
    # Observability (opt-in; see app/telemetry_otel.py). Exporter is configured
    # via the standard OTEL_EXPORTER_OTLP_ENDPOINT env var.
    relay_otel_enabled: bool = False
    # Provider routing (see app/routing.py). The chain is opt-in; empty means
    # one provider, one try, as before.
    relay_fallback_chain: str = ""            # e.g. "openai:gpt-4o-mini,ollama:llama3.2"
    relay_provider_timeout_s: float = 60.0    # per attempt; time-to-first-chunk for streams
    relay_breaker_failures: int = 3           # consecutive failures that open a circuit
    relay_breaker_reset_s: float = 30.0       # how long a circuit stays open before a trial


@lru_cache
def get_settings() -> Settings:
    return Settings()
