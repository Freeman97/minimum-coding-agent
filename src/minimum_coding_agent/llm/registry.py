"""Registry of chat model providers selected by ``provider.name``.

The registry is the extension point of the model access layer: the runtime only
asks for a :class:`~langchain_core.language_models.BaseChatModel`, while adding a
provider means registering one more implementation (see ``docs/providers.md``).
"""

from __future__ import annotations

from collections.abc import Mapping

from langchain_core.language_models import BaseChatModel

from minimum_coding_agent.config.settings import ProviderSettings
from minimum_coding_agent.llm.base import ChatModelProvider
from minimum_coding_agent.llm.errors import (
    DuplicateProviderError,
    ProviderContractError,
    UnknownProviderError,
)


class ProviderRegistry:
    """Collection of model providers, keyed by their unique provider name."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._providers: dict[str, ChatModelProvider] = {}

    def register(self, provider: ChatModelProvider) -> None:
        """Register a provider under its own ``name``.

        Args:
            provider: Provider instance that satisfies :class:`ChatModelProvider`.

        Raises:
            ProviderContractError: If the provider does not satisfy the contract.
            DuplicateProviderError: If the name is already registered.
        """
        name = getattr(provider, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise ProviderContractError(
                "provider contract violation: 'name' must be a non-empty string"
            )
        if not callable(getattr(provider, "create_model", None)):
            raise ProviderContractError(
                f"provider contract violation: {name!r} must define a callable "
                "create_model(settings, *, environ) method"
            )
        if not isinstance(provider, ChatModelProvider):
            raise ProviderContractError(
                f"provider {name!r} does not satisfy the ChatModelProvider contract"
            )
        if name in self._providers:
            raise DuplicateProviderError(name)
        self._providers[name] = provider

    def names(self) -> tuple[str, ...]:
        """Return the names of all registered providers.

        Returns:
            The provider names in alphabetical order.
        """
        return tuple(sorted(self._providers))

    def get(self, name: str) -> ChatModelProvider:
        """Return the provider registered under ``name``.

        Args:
            name: Provider name read from ``provider.name``.

        Returns:
            The matching provider.

        Raises:
            UnknownProviderError: If no provider is registered under ``name``.
        """
        provider = self._providers.get(name)
        if provider is None:
            raise UnknownProviderError(name, self.names())
        return provider

    def create_model(
        self,
        settings: ProviderSettings,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> BaseChatModel:
        """Create a chat model with the provider selected by ``settings.name``.

        Args:
            settings: The ``provider`` section of the application configuration.
            environ: Environment mapping used to resolve ``api_key_env``;
                defaults to ``os.environ``.

        Returns:
            The chat model created by the selected provider.

        Raises:
            UnknownProviderError: If ``settings.name`` is not registered.
        """
        provider = self._providers.get(settings.name)
        if provider is None:
            raise UnknownProviderError(settings.name, self.names())
        return provider.create_model(settings, environ=environ)

    def __contains__(self, name: object) -> bool:
        """Return whether a provider is registered under ``name``.

        Args:
            name: Candidate provider name.

        Returns:
            ``True`` if a provider with that name is registered.
        """
        return name in self._providers

    def __len__(self) -> int:
        """Return the number of registered providers.

        Returns:
            The provider count.
        """
        return len(self._providers)
