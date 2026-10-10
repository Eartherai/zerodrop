"""Settings validation (model ids). Never reads the real environment or a .env file."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_settings import PydanticBaseSettingsSource

from zerodrop.config import SUPPORTED_MODEL_PREFIXES, Settings


class IsolatedSettings(Settings):
    """`Settings` with only init arguments as a source: no environment, no .env, no secrets dir."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[Any],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def test_default_model_is_supported() -> None:
    default = Settings.model_fields["model"].default
    assert default == "claude-opus-5-5"
    assert IsolatedSettings().model == default


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
        "claude-sonnet-5",
        "claude-fable-5-1",
        "claude-fable-5",
        "claude-haiku-5-5",
    ],
)
def test_current_model_families_are_accepted(model: str) -> None:
    assert IsolatedSettings(model=model).model == model


def test_surrounding_whitespace_is_stripped() -> None:
    assert IsolatedSettings(model="  claude-sonnet-5-5\n").model == "claude-sonnet-5-5"


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-4-8",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-3-5-sonnet",
        "opus-5",
        "gpt-5",
        "",
        "   ",
    ],
)
def test_unsupported_models_are_rejected_with_a_clear_error(model: str) -> None:
    with pytest.raises(ValidationError) as info:
        IsolatedSettings(model=model)
    errors = info.value.errors()
    assert [e["loc"] for e in errors] == [("model",)]
    message = errors[0]["msg"]
    assert f"unsupported model {model!r}" in message
    assert "adaptive thinking" in message and "effort" in message
    for prefix in SUPPORTED_MODEL_PREFIXES:
        assert f"{prefix}*" in message


def test_the_prefix_list_is_the_documented_one() -> None:
    assert SUPPORTED_MODEL_PREFIXES == (
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-fable-5",
        "claude-haiku-5",
    )


def test_other_fields_are_unaffected() -> None:
    settings = IsolatedSettings(model="claude-haiku-5-5", max_llm_calls=3, max_rate_limit_waits=7)
    assert (settings.max_llm_calls, settings.max_rate_limit_waits) == (3, 7)
    assert settings.effort_plan == "medium" and settings.batch_size == 50
