"""Unit tests for the streaming chat wrapper."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import Field

import minimum_coding_agent.llm.streaming as streaming_module
from minimum_coding_agent.llm.errors import ModelCallCategory, ModelCallError
from minimum_coding_agent.llm.streaming import (
    MessageComplete,
    ModelStreamEvent,
    TextDelta,
    stream_chat,
)


class _ScriptedStreamModel(BaseChatModel):
    """Test double that streams scripted chunks and optionally raises an error."""

    script: list[AIMessageChunk] = Field(default_factory=list)
    failure: Any = None

    @property
    def _llm_type(self) -> str:
        return "test-scripted-stream"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("this test double only supports astream")

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in self.script:
            yield ChatGenerationChunk(message=chunk)
        if self.failure is not None:
            raise self.failure


class _DirectStreamModel(BaseChatModel):
    """Test double that implements ``astream`` directly, bypassing the base loop."""

    chunks: list[AIMessageChunk] = Field(default_factory=list)
    received_input: Any = None
    received_config: Any = None
    astream_calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "test-direct-stream"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("this test double only supports astream")

    async def astream(  # type: ignore[override]
        self,
        model_input: Any,
        config: Any = None,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessageChunk]:
        self.astream_calls += 1
        self.received_input = model_input
        self.received_config = config
        for chunk in self.chunks:
            yield chunk


async def _collect(
    model: Runnable[Any, Any],
    messages: Sequence[BaseMessage] | None = None,
    *,
    config: RunnableConfig | None = None,
) -> list[ModelStreamEvent]:
    payload = list(messages) if messages is not None else [HumanMessage(content="hi")]
    return [event async for event in stream_chat(model, payload, config=config)]


@pytest.mark.asyncio
async def test_stream_chat_yields_text_deltas_in_order() -> None:
    model = _ScriptedStreamModel(
        script=[AIMessageChunk(content="Hel"), AIMessageChunk(content="lo")]
    )

    events = await _collect(model)

    deltas = [event for event in events if isinstance(event, TextDelta)]
    assert deltas == [TextDelta("Hel"), TextDelta("lo")]
    assert deltas[0] is not deltas[1]
    assert isinstance(events[-1], MessageComplete)


@pytest.mark.asyncio
async def test_stream_chat_returns_aggregated_final_message() -> None:
    model = _ScriptedStreamModel(
        script=[AIMessageChunk(content="Hello "), AIMessageChunk(content="world")]
    )

    events = await _collect(model)

    complete = [event for event in events if isinstance(event, MessageComplete)]
    assert len(complete) == 1
    assert complete[0] is events[-1]
    assert complete[0].message.text == "Hello world"
    assert complete[0].message.content == "Hello world"


@pytest.mark.asyncio
async def test_stream_chat_ignores_chunks_without_text() -> None:
    model = _ScriptedStreamModel(
        script=[
            AIMessageChunk(content=""),
            AIMessageChunk(content="answer"),
        ]
    )

    events = await _collect(model)

    deltas = [event for event in events if isinstance(event, TextDelta)]
    assert deltas == [TextDelta("answer")]
    assert events[-1].message.text == "answer"


@pytest.mark.asyncio
async def test_stream_chat_supports_list_content_blocks() -> None:
    model = _ScriptedStreamModel(
        script=[
            AIMessageChunk(content=[{"type": "text", "text": "Hello "}]),
            AIMessageChunk(content="world"),
        ]
    )

    events = await _collect(model)

    deltas = [event for event in events if isinstance(event, TextDelta)]
    assert deltas == [TextDelta("Hello "), TextDelta("world")]
    assert events[-1].message.text == "Hello world"


@pytest.mark.asyncio
async def test_stream_chat_aggregates_tool_call_chunks() -> None:
    model = _ScriptedStreamModel(
        script=[
            AIMessageChunk(content="Checking the weather"),
            AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": "get_weather", "args": '{"city":', "id": "call_1", "index": 0}
                ],
            ),
            AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": None, "args": ' "Paris"}', "id": None, "index": 0}],
            ),
        ]
    )

    events = await _collect(model)

    message = events[-1].message
    assert message.text == "Checking the weather"
    assert len(message.tool_calls) == 1
    tool_call = message.tool_calls[0]
    assert tool_call["name"] == "get_weather"
    assert tool_call["args"] == {"city": "Paris"}
    assert tool_call["id"] == "call_1"


@pytest.mark.asyncio
async def test_stream_chat_classifies_mid_stream_failure_with_partial_text() -> None:
    failure = TimeoutError("read timed out")
    model = _ScriptedStreamModel(
        script=[AIMessageChunk(content="partial "), AIMessageChunk(content="answer")],
        failure=failure,
    )
    received: list[ModelStreamEvent] = []

    with pytest.raises(ModelCallError) as exc_info:
        async for event in stream_chat(model, [HumanMessage(content="hi")]):
            received.append(event)

    error = exc_info.value
    assert error.category is ModelCallCategory.TIMEOUT
    assert error.partial_text == "partial answer"
    assert received == [TextDelta("partial "), TextDelta("answer")]
    assert error.__cause__ is failure
    assert error.retryable is True


@pytest.mark.asyncio
async def test_stream_chat_classifies_failure_before_first_delta() -> None:
    failure = TimeoutError("connection timed out")
    model = _ScriptedStreamModel(failure=failure)
    received: list[ModelStreamEvent] = []

    with pytest.raises(ModelCallError) as exc_info:
        async for event in stream_chat(model, [HumanMessage(content="hi")]):
            received.append(event)

    assert exc_info.value.category is ModelCallCategory.TIMEOUT
    assert exc_info.value.partial_text == ""
    assert received == []


@pytest.mark.asyncio
async def test_stream_chat_rejects_empty_stream() -> None:
    model = _DirectStreamModel(chunks=[])

    with pytest.raises(ModelCallError) as exc_info:
        await _collect(model)

    error = exc_info.value
    assert error.category is ModelCallCategory.RESPONSE
    assert "empty stream" in error.message
    assert error.partial_text == ""
    assert error.retryable is True


@pytest.mark.asyncio
async def test_stream_chat_rejects_empty_stream_from_base_model() -> None:
    model = _ScriptedStreamModel()

    with pytest.raises(ModelCallError) as exc_info:
        await _collect(model)

    error = exc_info.value
    assert error.category is ModelCallCategory.RESPONSE
    assert "empty stream" in error.message
    assert isinstance(error.__cause__, ValueError)


@pytest.mark.asyncio
async def test_stream_chat_keeps_unrelated_value_error_as_unknown() -> None:
    failure = ValueError("invalid request parameters")
    model = _ScriptedStreamModel(failure=failure)

    with pytest.raises(ModelCallError) as exc_info:
        await _collect(model)

    assert exc_info.value.category is ModelCallCategory.UNKNOWN
    assert exc_info.value.__cause__ is failure


@pytest.mark.asyncio
async def test_stream_chat_rejects_unparseable_final_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _broken(_: BaseMessage) -> BaseMessage:
        raise ValueError("cannot decode protocol payload")

    monkeypatch.setattr(streaming_module, "message_chunk_to_message", _broken)
    model = _ScriptedStreamModel(script=[AIMessageChunk(content="draft answer")])

    with pytest.raises(ModelCallError) as exc_info:
        await _collect(model)

    error = exc_info.value
    assert error.category is ModelCallCategory.RESPONSE
    assert "cannot assemble" in error.message
    assert error.partial_text == "draft answer"
    assert isinstance(error.__cause__, ValueError)


@pytest.mark.asyncio
async def test_stream_chat_reraises_classified_error_unchanged() -> None:
    failure = ModelCallError(
        "model endpoint rejected the credentials",
        category=ModelCallCategory.AUTHENTICATION,
        hint="check provider.api_key_env",
        retryable=False,
    )
    model = _ScriptedStreamModel(script=[AIMessageChunk(content="hi")], failure=failure)

    with pytest.raises(ModelCallError) as exc_info:
        await _collect(model)

    assert exc_info.value is failure


@pytest.mark.asyncio
async def test_stream_chat_does_not_swallow_cancellation() -> None:
    model = _ScriptedStreamModel(
        script=[AIMessageChunk(content="start")], failure=asyncio.CancelledError()
    )
    received: list[ModelStreamEvent] = []

    with pytest.raises(asyncio.CancelledError):
        async for event in stream_chat(model, [HumanMessage(content="hi")]):
            received.append(event)

    assert received == [TextDelta("start")]


@pytest.mark.asyncio
async def test_stream_chat_delegates_to_async_stream() -> None:
    model = _DirectStreamModel(chunks=[AIMessageChunk(content="hi")])
    config: RunnableConfig = {"tags": ["test"], "metadata": {"case": "delegation"}}

    events = await _collect(model, [HumanMessage(content="hello")], config=config)

    assert model.astream_calls == 1
    assert [message.content for message in model.received_input] == ["hello"]
    assert model.received_config["tags"] == ["test"]
    assert isinstance(events[-1], MessageComplete)
    assert events[-1].message.text == "hi"


@pytest.mark.asyncio
async def test_stream_chat_accepts_bound_model_runnable() -> None:
    model = _ScriptedStreamModel(
        script=[AIMessageChunk(content="bound "), AIMessageChunk(content="reply")]
    )
    bound = model.bind(stop=["END"])

    events = await _collect(bound)

    assert events[0] == TextDelta("bound ")
    assert events[-1].message.text == "bound reply"
