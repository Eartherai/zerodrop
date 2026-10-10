"""Runtime settings, read from the environment / a git-ignored .env file only."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Model access: a dedicated variable so Claude Code never picks it up as ANTHROPIC_API_KEY.
    zerodrop_anthropic_key: SecretStr | None = None
    model: str = "claude-opus-5-5"
    effort_plan: str = "medium"  # mapping and diagnosis
    effort_light: str = "low"  # small classification-style calls

    # Hard limits per run.
    max_llm_calls: int = 30
    max_cost_usd: float = 1.50
    max_wall_seconds: int = 900
    max_replans: int = 3
    max_attempts_per_request: int = 6

    # Endpoints.
    source_url: str = "http://127.0.0.1:8701"
    target_url: str = "http://127.0.0.1:8702"
    target_token: SecretStr = SecretStr("nb_live_local_demo_token")
    target_token_file: str | None = None  # rotated credentials are re-read from here once on 401

    # Engine.
    batch_size: int = 50
    http_timeout_s: float = 2.0
    db_path: str = "zerodrop.db"

    # Neatlogs reads NEATLOGS_API_KEY itself; listed here only for documentation.
    neatlogs_api_key: SecretStr | None = Field(default=None, repr=False)


def get_settings() -> Settings:
    return Settings()
