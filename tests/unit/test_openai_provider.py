"""Unit tests for the OpenAI-compatible provider and its configuration mapping."""

from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI

from minimum_coding_agent.config.settings import ProviderSettings
from minimum_coding_agent.llm.errors import ProviderConfigurationError
from minimum_coding_agent.llm.openai_compatible import OpenAICompatibleProvider


def make_provider_settings(**overrides: object) -> ProviderSettings:
    values: dict[str, object] = {
        "name": "openai-compatible",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key": "sk-test-123456",
        "temperature": 0.3,
        "max_tokens": 2048,
        "timeout_seconds": 42.0,
    }
    values.update(overrides)
    return ProviderSettings.model_validate(values)


def test_settings_are_mapped_to_chat_openai_parameters() -> None:
    model = OpenAICompatibleProvider().create_model(make_provider_settings())

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-chat"
    assert model.openai_api_base == "https://api.deepseek.com"
    assert model.temperature == 0.3
    assert model.max_tokens == 2048
    assert model.request_timeout == 42.0
    assert model.max_retries == 0
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == "sk-test-123456"


def test_defaults_are_mapped() -> None:
    settings = ProviderSettings(
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key="sk-test-123456",
    )

    model = OpenAICompatibleProvider().create_model(settings)

    assert model.temperature == 0.0
    assert model.max_tokens is None
    assert model.request_timeout == 60.0


def test_api_key_is_resolved_from_the_supplied_environment() -> None:
    settings = make_provider_settings(api_key=None, api_key_env="TEAM_API_KEY")

    model = OpenAICompatibleProvider().create_model(
        settings, environ={"TEAM_API_KEY": "sk-env-123456"}
    )

    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == "sk-env-123456"


@pytest.mark.parametrize(
    "overrides",
    [
        {"api_key": None},  # no key at all
        {"base_url": None},
        {"model": None},
    ],
    ids=["missing-api-key", "missing-base-url", "missing-model"],
)
def test_incomplete_configuration_is_rejected(overrides: dict[str, object]) -> None:
    settings = make_provider_settings(**overrides)

    with pytest.raises(ProviderConfigurationError) as excinfo:
        OpenAICompatibleProvider().create_model(settings, environ={})

    message = str(excinfo.value)
    assert "cannot create the openai-compatible provider" in message
    assert "sk-" not in message


def test_unset_api_key_environment_variable_is_rejected() -> None:
    settings = make_provider_settings(api_key=None, api_key_env="TEAM_API_KEY")

    with pytest.raises(ProviderConfigurationError):
        OpenAICompatibleProvider().create_model(settings, environ={})


def test_provider_name_matches_registry_key() -> None:
    assert OpenAICompatibleProvider().name == "openai-compatible"
