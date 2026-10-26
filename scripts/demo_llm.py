"""Offline demo of the M1 model access layer.

Run with ``make demo-llm`` or ``.tools/uv run python scripts/demo_llm.py``.
The demo maps an OpenAI-compatible provider configuration to a ``ChatOpenAI``
instance, streams a scripted model through the shared streaming wrapper, and
shows that classified errors never reveal secrets. No network request is made.
"""

from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage

from minimum_coding_agent.config.settings import ProviderSettings
from minimum_coding_agent.llm.defaults import create_default_registry
from minimum_coding_agent.llm.errors import classify_model_error
from minimum_coding_agent.llm.openai_compatible import OpenAICompatibleProvider
from minimum_coding_agent.llm.scripted import ScriptedChatModel, ScriptedToolCall, ScriptedTurn
from minimum_coding_agent.llm.streaming import MessageComplete, TextDelta, stream_chat

#: Inline fake key used to demonstrate masking; it is never sent anywhere.
DEMO_API_KEY = "sk-demo-key-never-used"


async def main() -> int:
    """Print the delivered M1 capabilities without network access.

    Returns:
        The process exit code.
    """
    registry = create_default_registry()
    print(f"1. registered providers: {', '.join(registry.names())}")

    settings = ProviderSettings(
        name="openai-compatible",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key=DEMO_API_KEY,
        temperature=0.0,
        max_tokens=4096,
        timeout_seconds=60.0,
    )
    model = OpenAICompatibleProvider().create_model(settings)
    print("2. configuration -> ChatOpenAI mapping (offline, no request is sent):")
    print(f"   model={model.model_name} base_url={model.openai_api_base}")
    print(
        f"   temperature={model.temperature} max_tokens={model.max_tokens} "
        f"timeout={model.request_timeout} max_retries={model.max_retries}"
    )
    print(f"   api_key=<{'set' if model.openai_api_key else 'missing'}>, never printed")

    scripted = ScriptedChatModel(
        turns=(
            ScriptedTurn(chunks=("I will inspect ", "the workspace first.")),
            ScriptedTurn(
                tool_calls=(ScriptedToolCall(name="tree", args={"path": "."}, id="call_demo_1"),)
            ),
        )
    )
    print("3. streaming through the shared wrapper (scripted model, no network):")
    for call_number in (1, 2):
        print(f"   call {call_number} deltas: ", end="")
        final = None
        async for event in stream_chat(scripted, [HumanMessage(content="demo")]):
            if isinstance(event, TextDelta):
                print(repr(event.text), end=" ", flush=True)
            elif isinstance(event, MessageComplete):
                final = event.message
        print()
        if final is not None:
            print(f"   final content={final.content!r} tool_calls={final.tool_calls}")

    print("4. classified error with redaction:")
    error = classify_model_error(RuntimeError(f"upstream failed with api_key={DEMO_API_KEY}"))
    print(f"   category={error.category.value} retryable={error.retryable}")
    print(f"   message={error.message}")
    print(f"   hint={error.hint}")
    if DEMO_API_KEY in error.message:
        print("   ERROR: the demo key leaked into the error message")
        return 1
    print("demo finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
