"""Deterministic scripted chat model used as an offline test double.

:class:`ScriptedChatModel` replaces a real provider in tests: every model call
plays the next :class:`ScriptedTurn` from a preset script, replaying its text
fragments as stream chunks and emitting its scripted tool calls. Production code
depends only on ``BaseChatModel`` and never imports this module.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field, PrivateAttr


@dataclass(frozen=True)
class ScriptedToolCall:
    """A tool call requested by a scripted turn.

    Attributes:
        name: Name of the tool to call.
        args: JSON-compatible arguments passed to the tool.
        id: Tool call identifier. An empty string asks the model to generate a
            deterministic ``call_<turn>_<index>`` identifier when the turn is
            played.
    """

    name: str
    args: dict[str, Any]
    id: str = ""


@dataclass(frozen=True)
class ScriptedTurn:
    """One scripted assistant response.

    Attributes:
        chunks: Text fragments in streaming order; the final content of the
            response is their concatenation.
        tool_calls: Tool calls emitted after the text fragments.
    """

    chunks: tuple[str, ...] = ()
    tool_calls: tuple[ScriptedToolCall, ...] = ()


class ScriptedExhaustedError(RuntimeError):
    """Raised when the model is asked to play a turn outside the script.

    The model raises this error when the script is empty or when every scripted
    turn has already been consumed and ``repeat_last`` is disabled.
    """


class ScriptedChatModel(BaseChatModel):
    """Chat model that plays a preset script of assistant turns.

    The model is deterministic and fully offline. Each invocation consumes one
    turn from ``turns`` and raises :class:`ScriptedExhaustedError` once the
    script is exhausted, unless ``repeat_last`` is enabled. ``invoke`` and
    ``ainvoke`` return the complete response, while ``astream`` replays the same
    response as text fragments followed by tool call chunks, so aggregating the
    streamed chunks reproduces the non-streaming message.

    Stop sequences and callback managers are accepted for interface
    compatibility but ignored, because scripted turns are fixed in advance.

    Attributes:
        turns: Scripted turns played in order, one per model invocation.
        repeat_last: Whether the final turn is replayed after the script is
            exhausted instead of raising :class:`ScriptedExhaustedError`.
        seen_messages: Message lists received from the caller, recorded once per
            model invocation; tests use this to assert what the runtime sent.
    """

    turns: tuple[ScriptedTurn, ...] = ()
    repeat_last: bool = False
    seen_messages: list[list[BaseMessage]] = Field(default_factory=list)

    _call_count: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        """Return the model type identifier."""
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Play the next scripted turn as a single chat result."""
        turn, tool_calls = self._next_response(messages)
        message = AIMessage(content="".join(turn.chunks), tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Play the next scripted turn as ordered response chunks."""
        turn, tool_calls = self._next_response(messages)
        for fragment in turn.chunks:
            yield ChatGenerationChunk(message=AIMessageChunk(content=fragment))
        for index, tool_call in enumerate(tool_calls):
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": tool_call["name"],
                            "args": json.dumps(tool_call["args"]),
                            "id": tool_call["id"],
                            "index": index,
                        }
                    ],
                )
            )
        if not turn.chunks and not tool_calls:
            # Yield one empty chunk so stream consumers can always aggregate.
            yield ChatGenerationChunk(message=AIMessageChunk(content=""))

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> ScriptedChatModel:
        """Return this model unchanged.

        Scripted turns already encode their tool calls, so binding tool schemas
        does not change model behavior. The method exists because the agent
        runtime binds tools to every chat model it creates.

        Args:
            tools: Tool definitions proposed by the caller; unused because the
                script carries the tool calls.
            tool_choice: Forced tool choice requested by the caller; unused for
                the same reason.
            **kwargs: Additional binding options accepted for interface
                compatibility.

        Returns:
            This model instance, which remains usable with ``invoke`` and
            ``astream``.
        """
        return self

    def _next_response(
        self, messages: list[BaseMessage]
    ) -> tuple[ScriptedTurn, list[dict[str, Any]]]:
        """Record incoming messages and resolve the next scripted turn."""
        self.seen_messages.append(list(messages))
        call_index, turn = self._next_turn()
        tool_calls = [
            {
                "name": tool_call.name,
                "args": dict(tool_call.args),
                "id": tool_call.id or f"call_{call_index}_{call_index_in_turn}",
                "type": "tool_call",
            }
            for call_index_in_turn, tool_call in enumerate(turn.tool_calls)
        ]
        return turn, tool_calls

    def _next_turn(self) -> tuple[int, ScriptedTurn]:
        """Return the play index and next turn, or raise ScriptedExhaustedError."""
        if not self.turns:
            raise ScriptedExhaustedError(
                "ScriptedChatModel has no turns: 0 turns scripted; "
                "provide at least one ScriptedTurn."
            )
        call_index = self._call_count
        if call_index >= len(self.turns):
            if not self.repeat_last:
                raise ScriptedExhaustedError(
                    f"ScriptedChatModel script exhausted: {len(self.turns)} "
                    f"turn(s) scripted, but call {call_index + 1} was requested; "
                    "set repeat_last=True to replay the final turn."
                )
            turn_index = len(self.turns) - 1
        else:
            turn_index = call_index
        self._call_count += 1
        return call_index, self.turns[turn_index]
