"""Unit tests for the deterministic scripted chat model test double."""

from __future__ import annotations

import json
from functools import reduce
from operator import add

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from minimum_coding_agent.llm.scripted import (
    ScriptedChatModel,
    ScriptedExhaustedError,
    ScriptedToolCall,
    ScriptedTurn,
)


def _model(*turns: ScriptedTurn, repeat_last: bool = False) -> ScriptedChatModel:
    """Build a scripted model that plays the given turns."""
    return ScriptedChatModel(turns=turns, repeat_last=repeat_last)


def test_llm_type_is_scripted() -> None:
    assert _model(ScriptedTurn(chunks=("x",)))._llm_type == "scripted"


@pytest.mark.asyncio
async def test_astream_replays_text_fragments_in_script_order() -> None:
    model = _model(ScriptedTurn(chunks=("Hello", " world")))

    chunks = [chunk async for chunk in model.astream("hi")]

    fragments = [chunk.content for chunk in chunks if chunk.content]
    assert fragments == ["Hello", " world"]
    assert "".join(str(chunk.content) for chunk in chunks) == "Hello world"


@pytest.mark.asyncio
async def test_ainvoke_returns_final_content_and_records_seen_messages() -> None:
    model = _model(ScriptedTurn(chunks=("Done", "!")))

    reply = await model.ainvoke([HumanMessage(content="task")])

    assert isinstance(reply, AIMessage)
    assert reply.content == "Done!"
    assert reply.tool_calls == []
    assert len(model.seen_messages) == 1
    assert [message.content for message in model.seen_messages[0]] == ["task"]


@pytest.mark.asyncio
async def test_astream_records_seen_messages() -> None:
    model = _model(ScriptedTurn(chunks=("ok",)))

    _ = [chunk async for chunk in model.astream([HumanMessage(content="stream task")])]

    assert len(model.seen_messages) == 1
    assert model.seen_messages[0][0].content == "stream task"


@pytest.mark.asyncio
async def test_ainvoke_returns_scripted_tool_calls() -> None:
    model = _model(
        ScriptedTurn(
            tool_calls=(
                ScriptedToolCall(name="view", args={"path": "a.py"}),
                ScriptedToolCall(name="grep", args={"query": "needle"}, id="explicit-id"),
            )
        )
    )

    reply = await model.ainvoke("look around")

    assert reply.tool_calls == [
        {
            "name": "view",
            "args": {"path": "a.py"},
            "id": "call_0_0",
            "type": "tool_call",
        },
        {
            "name": "grep",
            "args": {"query": "needle"},
            "id": "explicit-id",
            "type": "tool_call",
        },
    ]


@pytest.mark.asyncio
async def test_astream_emits_tool_call_chunks_after_text_fragments() -> None:
    model = _model(
        ScriptedTurn(
            chunks=("Calling ", "the tool."),
            tool_calls=(ScriptedToolCall(name="view", args={"path": "a.py"}),),
        )
    )

    chunks = [chunk async for chunk in model.astream("hi")]
    tool_chunks = [tool_chunk for chunk in chunks for tool_chunk in chunk.tool_call_chunks]

    assert len(tool_chunks) == 1
    assert tool_chunks[0]["name"] == "view"
    assert json.loads(tool_chunks[0]["args"] or "{}") == {"path": "a.py"}
    assert tool_chunks[0]["id"] == "call_0_0"
    assert tool_chunks[0]["index"] == 0

    text_positions = [index for index, chunk in enumerate(chunks) if chunk.content]
    tool_positions = [index for index, chunk in enumerate(chunks) if chunk.tool_call_chunks]
    assert text_positions
    assert max(text_positions) < min(tool_positions)


@pytest.mark.asyncio
async def test_aggregated_chunks_match_ainvoke_content_and_tool_calls() -> None:
    turns = (
        ScriptedTurn(
            chunks=("Let me ", "check."),
            tool_calls=(
                ScriptedToolCall(name="view", args={"path": "a.py"}),
                ScriptedToolCall(name="grep", args={"query": "needle"}, id="explicit-id"),
            ),
        ),
    )
    expected = await _model(*turns).ainvoke("hi")

    chunks = [chunk async for chunk in _model(*turns).astream("hi")]
    aggregated = reduce(add, chunks)

    assert aggregated.content == expected.content
    assert aggregated.tool_calls == expected.tool_calls
    assert [tool_call["id"] for tool_call in aggregated.tool_calls] == [
        "call_0_0",
        "explicit-id",
    ]


@pytest.mark.asyncio
async def test_aggregated_tool_only_turn_matches_ainvoke() -> None:
    turns = (ScriptedTurn(tool_calls=(ScriptedToolCall(name="view", args={"path": "a.py"}),)),)
    expected = await _model(*turns).ainvoke("hi")

    aggregated = reduce(add, [chunk async for chunk in _model(*turns).astream("hi")])

    assert aggregated.content == expected.content
    assert aggregated.content == ""
    assert aggregated.tool_calls == expected.tool_calls


@pytest.mark.asyncio
async def test_turns_are_consumed_in_sequence() -> None:
    model = _model(ScriptedTurn(chunks=("first",)), ScriptedTurn(chunks=("second",)))

    assert (await model.ainvoke("a")).content == "first"
    assert (await model.ainvoke("b")).content == "second"
    assert len(model.seen_messages) == 2


@pytest.mark.asyncio
async def test_astream_consumes_the_same_turn_sequence() -> None:
    model = _model(ScriptedTurn(chunks=("first",)), ScriptedTurn(chunks=("second",)))

    contents = []
    for _ in range(2):
        chunks = [chunk async for chunk in model.astream("next")]
        contents.append(reduce(add, chunks).content)

    assert contents == ["first", "second"]


@pytest.mark.asyncio
async def test_repeat_last_replays_the_final_turn() -> None:
    model = _model(
        ScriptedTurn(chunks=("one",)),
        ScriptedTurn(chunks=("two",)),
        repeat_last=True,
    )

    contents = [(await model.ainvoke(str(index))).content for index in range(4)]

    assert contents == ["one", "two", "two", "two"]
    assert len(model.seen_messages) == 4


@pytest.mark.asyncio
async def test_exhausted_script_raises_with_scripted_turn_count() -> None:
    model = _model(ScriptedTurn(chunks=("only",)))

    await model.ainvoke("first call")
    with pytest.raises(ScriptedExhaustedError, match="1 turn"):
        await model.ainvoke("second call")


@pytest.mark.asyncio
async def test_astream_beyond_the_script_raises() -> None:
    model = _model(ScriptedTurn(chunks=("only",)))

    _ = [chunk async for chunk in model.astream("first call")]
    with pytest.raises(ScriptedExhaustedError, match="1 turn"):
        _ = [chunk async for chunk in model.astream("second call")]


@pytest.mark.asyncio
async def test_empty_script_raises() -> None:
    with pytest.raises(ScriptedExhaustedError, match="0 turns"):
        await _model().ainvoke("anything")


@pytest.mark.asyncio
async def test_bind_tools_returns_same_usable_model() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "view",
                "description": "View a file",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    model = _model(ScriptedTurn(chunks=("bound",)))

    bound = model.bind_tools(tools, tool_choice="any")

    assert bound is model
    assert (await bound.ainvoke("hi")).content == "bound"


@pytest.mark.asyncio
async def test_bound_model_still_streams() -> None:
    model = _model(ScriptedTurn(chunks=("streamed",)))

    bound = model.bind_tools([])
    aggregated = reduce(add, [chunk async for chunk in bound.astream("hi")])

    assert aggregated.content == "streamed"
