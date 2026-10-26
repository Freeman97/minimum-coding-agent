"""Model access layer: provider registry, streaming calls and offline test doubles.

The agent runtime and the interfaces depend on the public names re-exported here
and never on a specific model vendor. See ``docs/providers.md`` for the
configuration mapping and the provider extension contract.
"""

from minimum_coding_agent.llm.base import ChatModelProvider
from minimum_coding_agent.llm.defaults import create_chat_model, create_default_registry
from minimum_coding_agent.llm.errors import (
    DuplicateProviderError,
    LlmError,
    ModelCallCategory,
    ModelCallError,
    ProviderConfigurationError,
    ProviderContractError,
    UnknownProviderError,
    classify_model_error,
    redact_secret_text,
)
from minimum_coding_agent.llm.openai_compatible import OpenAICompatibleProvider
from minimum_coding_agent.llm.registry import ProviderRegistry
from minimum_coding_agent.llm.scripted import (
    ScriptedChatModel,
    ScriptedExhaustedError,
    ScriptedToolCall,
    ScriptedTurn,
)
from minimum_coding_agent.llm.streaming import (
    MessageComplete,
    ModelStreamEvent,
    TextDelta,
    stream_chat,
)

__all__ = [
    "ChatModelProvider",
    "DuplicateProviderError",
    "LlmError",
    "MessageComplete",
    "ModelCallCategory",
    "ModelCallError",
    "ModelStreamEvent",
    "OpenAICompatibleProvider",
    "ProviderConfigurationError",
    "ProviderContractError",
    "ProviderRegistry",
    "ScriptedChatModel",
    "ScriptedExhaustedError",
    "ScriptedToolCall",
    "ScriptedTurn",
    "TextDelta",
    "UnknownProviderError",
    "classify_model_error",
    "create_chat_model",
    "create_default_registry",
    "redact_secret_text",
    "stream_chat",
]
