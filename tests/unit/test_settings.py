"""Unit tests for the pydantic settings models."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from minimum_coding_agent.config.settings import REDACTED, Settings


def test_defaults_are_usable() -> None:
    settings = Settings()
    assert settings.provider.name == "openai-compatible"
    assert settings.provider.base_url is None
    assert settings.provider.model is None
    assert settings.provider.temperature == 0.0
    assert settings.provider.timeout_seconds == 60.0
    assert settings.workspace == Path(".")
    assert settings.instructions_file == "AGENT.md"
    assert settings.agent.max_iterations == 30
    assert settings.agent.context.max_tokens == 64000
    assert settings.tools.bash.confirm_dangerous_commands is True
    assert settings.tools.filesystem.enabled is True
    assert settings.mcp.servers == []


def test_required_fields_are_enforced() -> None:
    with pytest.raises(ValidationError, match="name"):
        Settings.model_validate({"mcp": {"servers": [{"transport": "stdio"}]}})


def test_empty_strings_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"provider": {"model": ""}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"instructions_file": ""})


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Settings.model_validate({"unknown": True})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Settings.model_validate({"provider": {"unknown": True}})


def test_api_key_and_api_key_env_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        Settings.model_validate(
            {"provider": {"api_key": "sk-inline", "api_key_env": "SOME_API_KEY"}}
        )


@pytest.mark.parametrize("temperature", [-0.1, 2.1, 5])
def test_temperature_must_stay_in_range(temperature: float) -> None:
    with pytest.raises(ValidationError, match="temperature"):
        Settings.model_validate({"provider": {"temperature": temperature}})


@pytest.mark.parametrize(
    ("section", "value"),
    [
        ("agent", {"max_iterations": 0}),
        ("agent", {"context": {"max_tokens": 10}}),
        ("provider", {"max_tokens": 0}),
    ],
)
def test_bounded_values_are_rejected(section: str, value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({section: value})


def test_workspace_string_is_coerced_to_path() -> None:
    settings = Settings.model_validate({"workspace": "some/dir"})
    assert settings.workspace == Path("some/dir")


def test_redacted_dict_masks_inline_secret() -> None:
    settings = Settings.model_validate({"provider": {"api_key": "sk-super-secret"}})
    redacted = settings.redacted_dict()
    assert redacted["provider"]["api_key"] == REDACTED
    serialized = json.dumps(redacted)
    assert "sk-super-secret" not in serialized
    assert "sk-super-secret" not in repr(settings.redacted_dict())


def test_redacted_dict_keeps_absent_secret_as_none() -> None:
    settings = Settings()
    assert settings.redacted_dict()["provider"]["api_key"] is None


def test_blank_inline_api_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        Settings.model_validate({"provider": {"api_key": "   "}})


@pytest.mark.parametrize("field", ["base_url", "api_key_env", "model"])
def test_blank_provider_strings_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        Settings.model_validate({"provider": {field: "   "}})


def test_blank_instructions_file_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        Settings.model_validate({"instructions_file": "   "})


def test_whitespace_environment_api_key_is_treated_as_missing() -> None:
    settings = Settings.model_validate({"provider": {"api_key_env": "TEAM_API_KEY"}})
    assert settings.provider.resolved_api_key({"TEAM_API_KEY": "   "}) is None


def test_redacted_dict_masks_mcp_server_environment_values() -> None:
    settings = Settings.model_validate(
        {
            "mcp": {
                "servers": [
                    {
                        "name": "echo",
                        "env": {"SERVICE_TOKEN": "mcp-secret", "LOG_LEVEL": "debug"},
                    }
                ]
            }
        }
    )
    redacted = settings.redacted_dict()
    server_env = redacted["mcp"]["servers"][0]["env"]
    assert server_env["SERVICE_TOKEN"] == REDACTED
    assert server_env["LOG_LEVEL"] == REDACTED
    assert "mcp-secret" not in json.dumps(redacted)


def test_resolved_api_key_prefers_inline_secret() -> None:
    settings = Settings.model_validate({"provider": {"api_key": "sk-inline"}})
    assert settings.provider.resolved_api_key({"OTHER": "value"}) == "sk-inline"


def test_resolved_api_key_reads_environment_variable() -> None:
    settings = Settings.model_validate({"provider": {"api_key_env": "TEAM_API_KEY"}})
    assert settings.provider.resolved_api_key({"TEAM_API_KEY": "sk-env"}) == "sk-env"


def test_resolved_api_key_returns_none_when_variable_is_missing() -> None:
    settings = Settings.model_validate({"provider": {"api_key_env": "TEAM_API_KEY"}})
    assert settings.provider.resolved_api_key({}) is None


def test_resolved_api_key_returns_none_without_credentials() -> None:
    assert Settings().provider.resolved_api_key({}) is None


def test_inline_secret_is_used_reports_inline_key() -> None:
    inline = Settings.model_validate({"provider": {"api_key": "sk-inline"}})
    environment = Settings.model_validate({"provider": {"api_key_env": "TEAM_API_KEY"}})
    assert inline.provider.inline_secret_is_used() is True
    assert environment.provider.inline_secret_is_used() is False


def test_secret_type_is_not_plain_in_repr() -> None:
    settings = Settings.model_validate({"provider": {"api_key": "sk-super-secret"}})
    assert isinstance(settings.provider.api_key, SecretStr)
    assert "sk-super-secret" not in repr(settings.provider)
