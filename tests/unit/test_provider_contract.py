"""Contract tests for the provider extension point (see ``docs/providers.md``)."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage
from providers import EchoProvider

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.llm.defaults import create_chat_model
from minimum_coding_agent.llm.errors import ProviderContractError, UnknownProviderError
from minimum_coding_agent.llm.registry import ProviderRegistry
from minimum_coding_agent.llm.scripted import ScriptedChatModel
from minimum_coding_agent.llm.streaming import MessageComplete, TextDelta, stream_chat

PROVIDER_DOCS = Path(__file__).resolve().parents[2] / "docs" / "providers.md"


def make_settings(provider_name: str = "echo-scripted", model: str = "demo-model") -> Settings:
    return Settings.model_validate(
        {
            "provider": {"name": provider_name, "model": model},
            "workspace": ".",
        }
    )


def test_documentation_uses_the_reusable_sample_provider() -> None:
    documentation = PROVIDER_DOCS.read_text(encoding="utf-8")

    assert "EchoProvider" in documentation
    assert "registry.register(EchoProvider())" in documentation
    assert "tests/fixtures/providers.py" in documentation


@pytest.mark.asyncio
async def test_registered_provider_is_selected_from_configuration() -> None:
    registry = ProviderRegistry()
    registry.register(EchoProvider())
    settings = make_settings(model="demo-model")

    model = create_chat_model(settings, registry=registry)

    assert isinstance(model, ScriptedChatModel)
    events = [event async for event in stream_chat(model, [HumanMessage(content="hello")])]
    deltas = [event.text for event in events if isinstance(event, TextDelta)]
    finals = [event for event in events if isinstance(event, MessageComplete)]
    assert "".join(deltas) == "echo from demo-model"
    assert len(finals) == 1
    assert finals[0].message.content == "echo from demo-model"


@pytest.mark.asyncio
async def test_registered_provider_supports_multiple_calls() -> None:
    registry = ProviderRegistry()
    registry.register(EchoProvider())
    model = create_chat_model(make_settings(), registry=registry)

    first = await model.ainvoke([HumanMessage(content="first")])
    second = await model.ainvoke([HumanMessage(content="second")])

    assert first.content == "echo from demo-model"
    assert second.content == "echo from demo-model"


def test_unknown_provider_in_configuration_is_reported() -> None:
    with pytest.raises(UnknownProviderError) as excinfo:
        create_chat_model(make_settings(provider_name="missing-provider"))

    message = str(excinfo.value)
    assert "unknown model provider 'missing-provider'" in message
    assert "openai-compatible" in message


def test_non_compliant_provider_is_rejected_at_registration() -> None:
    class _IncompleteProvider:
        name = "incomplete"

    with pytest.raises(ProviderContractError) as excinfo:
        ProviderRegistry().register(_IncompleteProvider())  # type: ignore[arg-type]

    assert "create_model" in str(excinfo.value)
