"""Central configuration. All secrets/settings come from environment variables or .env."""
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM (Groq) ---
    llm_provider: str = "groq"
    llm_model: str = "openai/gpt-oss-20b"
    llm_api_key: SecretStr | None = None  # SecretStr: never printed in logs/repr
    llm_strict_schema: bool = True
    llm_reasoning_effort: str = "low"  # only sent for openai/gpt-oss-* models
    llm_max_output_tokens: int = 4000  # for reasoning models this includes reasoning tokens
    llm_temperature: float = 0.1
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2  # SDK-level retries for connection errors / 429 / 5xx

    # --- Input limits ---
    min_inquiry_chars: int = 20
    max_inquiry_chars: int = 4000

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
