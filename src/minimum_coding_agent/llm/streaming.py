"""Streaming chat helper with classified, user-safe failure handling.

The agent runtime consumes model output through :func:`stream_chat`. The helper
turns LangChain message chunks into small events that renderers can consume
incrementally, and it converts provider failures into
:class:`~minimum_coding_agent.llm.errors.ModelCallError` values whose messages
never contain credentials. Text received before an interrupted stream is kept on
the error as ``partial_text`` so the caller does not lose visible output.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import NoReturn, cast

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    message_chunk_to_message,
)
from langchain_core.runnables import Runnable, RunnableConfig

from minimum_coding_agent.llm.errors import (
    ModelCallCategory,
    ModelCallError,
    classify_model_error,
)

__all__ = ["MessageComplete", "ModelStreamEvent", "TextDelta", "stream_chat"]

#: Error text LangChain uses when a chat model stream produced no chunks at all.
_EMPTY_STREAM_ERROR = "No generation chunks were returned"


@dataclass(frozen=True)
class TextDelta:
    """One incremental text fragment of a streaming model response.

    Attributes:
        text: Non-empty text fragment produced by the model.
    """

    text: str


@dataclass(frozen=True)
class MessageComplete:
    """The aggregated final message of a streaming model response.

    Attributes:
        message: Complete assistant message, including tool calls.
    """

    message: AIMessage


#: Event yielded by :func:`stream_chat` for a streaming model call.
ModelStreamEvent = TextDelta | MessageComplete


async def stream_chat(
    model: Runnable[LanguageModelInput, AIMessage],
    messages: Sequence[BaseMessage],
    *,
    config: RunnableConfig | None = None,
) -> AsyncIterator[ModelStreamEvent]:
    """Stream one chat completion and classify any provider failure.

    Every text fragment is yielded as a :class:`TextDelta` as soon as it
    arrives. When the stream ends normally, exactly one
    :class:`MessageComplete` carries the aggregated final message, including
    tool calls. If the stream breaks after some text was received, the failure
    is raised as a :class:`ModelCallError` whose ``partial_text`` holds that
    text; fragments already yielded remain available to the consumer.

    Args:
        model: Chat model created by a provider, or a runnable wrapping one
            (for example a model with tools bound to it).
        messages: Conversation sent to the model.
        config: Optional LangChain runnable configuration, for example tags or
            metadata.

    Yields:
        ModelStreamEvent: One :class:`TextDelta` per non-empty text fragment,
            followed by one :class:`MessageComplete` after the stream ends.

    Raises:
        ModelCallError: If the provider fails, returns an empty stream, or the
            final message cannot be assembled. Messages are sanitized and never
            contain API keys.
    """
    aggregated: AIMessageChunk | None = None
    received: list[str] = []
    empty_stream_failure: Exception | None = None

    try:
        async for raw_chunk in model.astream(list(messages), config=config):
            # A chat model runnable streams chunks even when typed as a plain runnable.
            chunk = cast(AIMessageChunk, raw_chunk)
            aggregated = _merge_chunk(aggregated, chunk)
            # ``text`` handles both plain string content and content-block lists.
            text = chunk.text
            if text:
                received.append(text)
                yield TextDelta(text)
    except ModelCallError:
        raise
    except Exception as exc:
        if aggregated is not None or not _is_empty_stream_failure(exc):
            _raise_classified_model_error(exc, partial_text="".join(received))
        # LangChain reports a stream without chunks as an error; report it below.
        empty_stream_failure = exc

    partial_text = "".join(received)
    if aggregated is None:
        raise ModelCallError(
            "the model returned an empty stream",
            category=ModelCallCategory.RESPONSE,
            hint="retry; check that provider.model supports streaming",
            retryable=True,
            partial_text=partial_text,
        ) from empty_stream_failure

    try:
        message = message_chunk_to_message(aggregated)
    except Exception as exc:
        raise ModelCallError(
            "cannot assemble the model response",
            category=ModelCallCategory.RESPONSE,
            hint="retry; check that the endpoint is OpenAI-compatible",
            retryable=True,
            partial_text=partial_text,
        ) from exc

    if not isinstance(message, AIMessage):
        raise ModelCallError(
            "the model response is not an assistant message",
            category=ModelCallCategory.RESPONSE,
            hint="retry; check that the endpoint is OpenAI-compatible",
            retryable=True,
            partial_text=partial_text,
        )
    yield MessageComplete(message)


def _merge_chunk(
    aggregated: AIMessageChunk | None, chunk: AIMessageChunk
) -> AIMessageChunk:
    """Merge one streamed chunk into the aggregated assistant message."""
    if aggregated is None:
        return chunk
    return aggregated + chunk


def _is_empty_stream_failure(exc: Exception) -> bool:
    """Tell whether the failure is LangChain reporting a stream without chunks."""
    return isinstance(exc, ValueError) and _EMPTY_STREAM_ERROR in str(exc)


def _raise_classified_model_error(exc: Exception, *, partial_text: str) -> NoReturn:
    """Classify a provider failure and raise it chained to the original error."""
    raise classify_model_error(exc, partial_text=partial_text) from exc
