"""Provider extension contract for chat models.

A provider converts validated :class:`~minimum_coding_agent.config.settings.ProviderSettings`
into a LangChain :class:`~langchain_core.language_models.BaseChatModel`. The agent
runtime, the tools and the interfaces only depend on ``BaseChatModel`` and never
on a specific vendor.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from langchain_core.language_models import BaseChatModel

from minimum_coding_agent.config.settings import ProviderSettings


@runtime_checkable
class ChatModelProvider(Protocol):
    """Contract that every model provider must satisfy.

    Attributes:
        name: Unique provider name selected by ``provider.name`` in the
            configuration, for example ``"openai-compatible"``.
    """

    @property
    def name(self) -> str:
        """Return the unique provider name used in ``provider.name``.

        Returns:
            The provider name.
        """

    def create_model(
        self,
        settings: ProviderSettings,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> BaseChatModel:
        """Create a LangChain chat model from validated provider settings.

        Args:
            settings: The ``provider`` section of the application configuration.
            environ: Environment mapping used to resolve ``api_key_env``;
                defaults to ``os.environ``.

        Returns:
            A chat model that supports ``invoke`` and ``astream`` calls.
        """
