"""Env-gated live smoke tests for the model access layer.

These tests call a real OpenAI-compatible endpoint and are excluded from the
default quality gate. Run them explicitly with ``make test-live`` after setting
``MCA_LIVE_BASE_URL``, ``MCA_LIVE_API_KEY`` and ``MCA_LIVE_MODEL``.
"""

from __future__ import annotations

import os

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from minimum_coding_agent.config.settings import ProviderSettings
from minimum_coding_agent.llm.openai_compatible import OpenAICompatibleProvider
from minimum_coding_agent.llm.streaming import MessageComplete, TextDelta, stream_chat

pytestmark = pytest.mark.live

ENV_BASE_URL = "MCA_LIVE_BASE_URL"
ENV_API_KEY = "MCA_LIVE_API_KEY"
ENV_MODEL = "MCA_LIVE_MODEL"
LIVE_ENV_VARS: tuple[str, ...] = (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL)


def live_model() -> tuple[BaseChatModel, ProviderSettings]:
    """Create a chat model for the live smoke tests.

    Returns:
        The configured chat model and the provider settings behind it.

    Raises:
        pytest.skip.Exception: If one of the ``MCA_LIVE_*`` variables is unset.
    """
    missing = [name for name in LIVE_ENV_VARS if not os.environ.get(name)]
    if missing:
        pytest.skip("live model endpoint is not configured; missing: " + ", ".join(missing))
    environ = {name: os.environ[name] for name in LIVE_ENV_VARS}
    settings = ProviderSettings(
        name="openai-compatible",
        base_url=environ[ENV_BASE_URL],
        api_key_env=ENV_API_KEY,
        model=environ[ENV_MODEL],
        temperature=0.0,
        max_tokens=256,
        timeout_seconds=90.0,
    )
    model = OpenAICompatibleProvider().create_model(settings, environ=environ)
    return model, settings


@pytest.mark.asyncio
async def test_live_streaming_smoke() -> None:
    model, _ = live_model()

    deltas: list[str] = []
    final = None
    async for event in stream_chat(
        model,
        [HumanMessage(content="Reply with exactly one short sentence: pong.")],
    ):
        if isinstance(event, TextDelta):
            deltas.append(event.text)
        else:
            assert isinstance(event, MessageComplete)
            final = event.message

    assert deltas, "expected incremental output from the live endpoint"
    assert final is not None
    assert isinstance(final.content, str)
    assert final.content.strip()


@tool
def echo_text(text: str) -> str:
    """Echo the given text back to the caller.

    Args:
        text: Text to echo.

    Returns:
        The unchanged text.
    """
    return text


@pytest.mark.asyncio
async def test_live_tool_calling_smoke() -> None:
    model, _ = live_model()
    bound_model = model.bind_tools([echo_text])

    final = None
    async for event in stream_chat(
        bound_model,  # type: ignore[arg-type]
        [HumanMessage(content="Call the echo_text tool with the text 'ping'.")],
    ):
        if isinstance(event, MessageComplete):
            final = event.message

    assert final is not None
    assert final.tool_calls, "the live endpoint did not return a tool call"
    assert final.tool_calls[0]["name"] == "echo_text"
    assert final.tool_calls[0]["args"].get("text") == "ping"
