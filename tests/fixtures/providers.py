"""Reusable test doubles referenced by the documentation and contract tests.

``docs/providers.md`` uses :class:`EchoProvider` as the canonical sample of the
provider extension contract; keeping the sample here means the documentation and
the test suite exercise the same code.
"""

from __future__ import annotations

from collections.abc import Mapping

from langchain_core.language_models import BaseChatModel

from minimum_coding_agent.config.settings import ProviderSettings
from minimum_coding_agent.llm.scripted import ScriptedChatModel, ScriptedTurn


class EchoProvider:
    """Provider contract sample that returns an offline scripted echo model.

    A real provider would return the chat model of its vendor; this sample keeps
    everything offline so the extension contract can be tested without network
    access.

    Attributes:
        name: Unique provider name, selected by ``provider.name``.
    """

    name = "echo-scripted"

    def create_model(
        self,
        settings: ProviderSettings,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> BaseChatModel:
        """Create a scripted chat model that echoes the configured model name.

        Args:
            settings: The ``provider`` section of the application configuration.
            environ: Unused environment mapping; kept for contract compatibility.

        Returns:
            A scripted chat model that repeats its reply on every call.
        """
        reply = f"echo from {settings.model or 'unnamed model'}"
        return ScriptedChatModel(
            turns=(ScriptedTurn(chunks=(reply,)),),
            repeat_last=True,
        )
