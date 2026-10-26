"""Integration tests across the model access layer (offline, no network)."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.llm.defaults import create_chat_model
from minimum_coding_agent.llm.scripted import ScriptedChatModel, ScriptedToolCall, ScriptedTurn
from minimum_coding_agent.llm.streaming import MessageComplete, TextDelta, stream_chat


def make_scripted_model() -> ScriptedChatModel:
    return ScriptedChatModel(
        turns=(
            ScriptedTurn(chunks=("I will inspect ", "the workspace.")),
            ScriptedTurn(
                tool_calls=(ScriptedToolCall(name="tree", args={"path": "."}),),
            ),
        )
    )


def split_events(events: list[object]) -> tuple[str, object | None]:
    deltas: list[str] = []
    final = None
    for event in events:
        if isinstance(event, TextDelta):
            deltas.append(event.text)
        elif isinstance(event, MessageComplete):
            final = event.message
    return "".join(deltas), final


@pytest.mark.asyncio
async def test_streamed_text_then_tool_call_across_layer() -> None:
    model = make_scripted_model()

    text_events = [event async for event in stream_chat(model, [HumanMessage(content="start")])]
    text, text_final = split_events(text_events)

    assert text == "I will inspect the workspace."
    assert text_final is not None
    assert text_final.content == "I will inspect the workspace."
    assert text_final.tool_calls == []

    tool_events = [event async for event in stream_chat(model, [HumanMessage(content="continue")])]
    tool_text, tool_final = split_events(tool_events)

    assert tool_text == ""
    assert tool_final is not None
    assert tool_final.tool_calls
    assert tool_final.tool_calls[0]["name"] == "tree"
    assert tool_final.tool_calls[0]["args"] == {"path": "."}


@pytest.mark.asyncio
async def test_stream_chat_accepts_a_tool_bound_model() -> None:
    model = make_scripted_model().bind_tools([])
    events = [event async for event in stream_chat(model, [HumanMessage(content="start")])]

    text, final = split_events(events)

    assert text == "I will inspect the workspace."
    assert final is not None


def test_default_factory_creates_configured_chat_model_offline() -> None:
    settings = Settings.model_validate(
        {
            "provider": {
                "base_url": "https://api.example.com",
                "model": "test-model",
                "api_key_env": "TEAM_API_KEY",
            }
        }
    )

    model = create_chat_model(settings, environ={"TEAM_API_KEY": "sk-test-123456"})

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "test-model"
    assert model.openai_api_base == "https://api.example.com"
