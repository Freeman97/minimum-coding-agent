"""Default provider registry and chat model factory.

This module is the temporary composition point of the model access layer until
the application composition root (``app.py``) lands in M3. The agent runtime
depends on the returned :class:`~langchain_core.language_models.BaseChatModel`
only.
"""

from __future__ import annotations

from collections.abc import Mapping

from langchain_core.language_models import BaseChatModel

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.llm.openai_compatible import OpenAICompatibleProvider
from minimum_coding_agent.llm.registry import ProviderRegistry


def create_default_registry() -> ProviderRegistry:
    """Create a registry with every built-in provider registered.

    Returns:
        A registry containing the ``openai-compatible`` provider.
    """
    registry = ProviderRegistry()
    registry.register(OpenAICompatibleProvider())
    return registry


def create_chat_model(
    settings: Settings,
    *,
    registry: ProviderRegistry | None = None,
    environ: Mapping[str, str] | None = None,
) -> BaseChatModel:
    """Create the chat model selected by the application configuration.

    The provider name is resolved through the registry, so an unregistered name
    surfaces as :class:`~minimum_coding_agent.llm.errors.UnknownProviderError`
    before any interface starts.

    Args:
        settings: Validated application settings.
        registry: Registry to select the provider from; defaults to
            :func:`create_default_registry`.
        environ: Environment mapping used to resolve ``provider.api_key_env``;
            defaults to ``os.environ``.

    Returns:
        The configured LangChain chat model.
    """
    selected = create_default_registry() if registry is None else registry
    return selected.create_model(settings.provider, environ=environ)
