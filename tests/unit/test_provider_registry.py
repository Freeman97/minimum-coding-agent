"""Unit tests for the provider registry and provider contract validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest
from langchain_core.language_models import BaseChatModel

from minimum_coding_agent.config.settings import ProviderSettings
from minimum_coding_agent.llm.defaults import create_default_registry
from minimum_coding_agent.llm.errors import (
    DuplicateProviderError,
    ProviderContractError,
    UnknownProviderError,
)
from minimum_coding_agent.llm.registry import ProviderRegistry


class _StubProvider:
    """Minimal valid provider that records the settings it receives."""

    def __init__(self, name: str = "stub") -> None:
        self.name = name
        self.calls: list[tuple[ProviderSettings, Mapping[str, str] | None]] = []

    def create_model(
        self,
        settings: ProviderSettings,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> BaseChatModel:
        self.calls.append((settings, environ))
        return cast(BaseChatModel, object())


def make_provider_settings(name: str = "stub") -> ProviderSettings:
    return ProviderSettings(
        name=name,
        base_url="https://api.example.com",
        model="test-model",
        api_key="sk-test-123456",
    )


def test_register_and_lookup() -> None:
    registry = ProviderRegistry()
    provider = _StubProvider()

    registry.register(provider)

    assert registry.names() == ("stub",)
    assert "stub" in registry
    assert len(registry) == 1
    assert registry.get("stub") is provider


def test_names_are_sorted_alphabetically() -> None:
    registry = ProviderRegistry()
    registry.register(_StubProvider(name="zeta"))
    registry.register(_StubProvider(name="alpha"))

    assert registry.names() == ("alpha", "zeta")


def test_create_model_uses_selected_provider_and_environment() -> None:
    registry = ProviderRegistry()
    provider = _StubProvider()
    registry.register(provider)
    settings = make_provider_settings()
    environment = {"TEAM_API_KEY": "sk-env"}

    model = registry.create_model(settings, environ=environment)

    assert model is not None
    assert provider.calls == [(settings, environment)]


def test_duplicate_registration_is_rejected() -> None:
    registry = ProviderRegistry()
    registry.register(_StubProvider(name="stub"))

    with pytest.raises(DuplicateProviderError) as excinfo:
        registry.register(_StubProvider(name="stub"))

    message = str(excinfo.value)
    assert "'stub'" in message
    assert "already registered" in message


def test_unknown_provider_lists_available_names() -> None:
    registry = ProviderRegistry()
    registry.register(_StubProvider(name="beta"))
    registry.register(_StubProvider(name="alpha"))

    with pytest.raises(UnknownProviderError) as excinfo:
        registry.get("missing")

    message = str(excinfo.value)
    assert "unknown model provider 'missing'" in message
    assert "available providers: alpha, beta" in message


def test_unknown_provider_with_empty_registry() -> None:
    with pytest.raises(UnknownProviderError) as excinfo:
        ProviderRegistry().get("missing")

    assert "available providers: <none>" in str(excinfo.value)


def test_default_registry_registers_openai_compatible_provider() -> None:
    registry = create_default_registry()

    assert registry.names() == ("openai-compatible",)
    assert registry.get("openai-compatible").name == "openai-compatible"


class _MissingNameProvider:
    def create_model(
        self,
        settings: ProviderSettings,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> BaseChatModel:
        raise AssertionError("must not be called")


class _BlankNameProvider:
    name = "   "

    def create_model(
        self,
        settings: ProviderSettings,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> BaseChatModel:
        raise AssertionError("must not be called")


class _NonStringNameProvider:
    name = 42

    def create_model(
        self,
        settings: ProviderSettings,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> BaseChatModel:
        raise AssertionError("must not be called")


class _MissingCreateModelProvider:
    name = "incomplete"


class _NonCallableCreateModelProvider:
    name = "incomplete"
    create_model = "not-a-callable"


@pytest.mark.parametrize(
    "provider",
    [
        object(),
        _MissingNameProvider(),
        _BlankNameProvider(),
        _NonStringNameProvider(),
        _MissingCreateModelProvider(),
        _NonCallableCreateModelProvider(),
    ],
    ids=[
        "plain-object",
        "missing-name",
        "blank-name",
        "non-string-name",
        "missing-create-model",
        "non-callable-create-model",
    ],
)
def test_contract_violations_are_rejected(provider: object) -> None:
    registry = ProviderRegistry()

    with pytest.raises(ProviderContractError) as excinfo:
        registry.register(provider)  # type: ignore[arg-type]

    assert "provider contract violation" in str(excinfo.value)
