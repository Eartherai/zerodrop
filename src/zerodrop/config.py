"""Runtime settings, read from the environment / a git-ignored .env file only."""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The LLM layer always sends adaptive thinking and an effort level; older model families reject them.
SUPPORTED_MODEL_PREFIXES: tuple[str, ...] = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-haiku-5",
)
GEMINI_MODEL_PREFIX = "gemini-"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Model access: a dedicated variable so Claude Code never picks it up as ANTHROPIC_API_KEY.
    zerodrop_anthropic_key: SecretStr | None = None
    model: str = "claude-opus-5-5"  # validated: must start with one of SUPPORTED_MODEL_PREFIXES
    effort_plan: str = "medium"  # mapping and diagnosis
    effort_light: str = "low"  # small classification-style calls
    # Second planner provider (planner mode "gemini"); Claude stays the default.
    zerodrop_gemini_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"  # validated: must start with GEMINI_MODEL_PREFIX

    # Hard limits per run.
    max_llm_calls: int = 30
    max_cost_usd: float = 1.50
    max_wall_seconds: int = 900
    max_replans: int = 3
    max_attempts_per_request: int = 6
    # 429 + Retry-After means "wait", not "broken": counted separately (the wall-clock cap still applies).
    max_rate_limit_waits: int = 40

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

    @field_validator("model")
    @classmethod
    def _supported_model(cls, value: str) -> str:
        model = value.strip()
        if not model.startswith(SUPPORTED_MODEL_PREFIXES):
            allowed = ", ".join(f"{prefix}*" for prefix in SUPPORTED_MODEL_PREFIXES)
            raise ValueError(
                f"unsupported model {value!r}: ZeroDrop always sends adaptive thinking and an effort "
                f"level, which older models reject; use a model id starting with one of {allowed} "
                "(default claude-opus-5-5)"
            )
        return model

    @field_validator("gemini_model")
    @classmethod
    def _gemini_model(cls, value: str) -> str:
        model = value.strip()
        if not model.startswith(GEMINI_MODEL_PREFIX) or model == GEMINI_MODEL_PREFIX:
            raise ValueError(
                f"unsupported Gemini model {value!r}: planner mode gemini needs a model id starting "
                f"with {GEMINI_MODEL_PREFIX}* (default gemini-3.8-flash)"
            )
        return model


def get_settings() -> Settings:
    return Settings()
