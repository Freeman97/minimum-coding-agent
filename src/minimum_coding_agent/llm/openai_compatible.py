"""OpenAI-compatible chat model provider.

The provider is a thin mapping from :class:`ProviderSettings` to
:class:`~langchain_openai.ChatOpenAI`. Any endpoint that speaks the OpenAI Chat
Completions API (DeepSeek, Ollama, vLLM, ...) can be used by changing
``provider.base_url`` and ``provider.model`` in the configuration.
"""

from __future__ import annotations

from collections.abc import Mapping

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from minimum_coding_agent.config.settings import ProviderSettings
from minimum_coding_agent.llm.errors import ProviderConfigurationError

#: Registry name of the built-in provider.
PROVIDER_NAME = "openai-compatible"


class OpenAICompatibleProvider:
    """Provider for endpoints speaking the OpenAI Chat Completions protocol.

    Attributes:
        name: The registry name, ``"openai-compatible"``.
    """

    name = PROVIDER_NAME

    def create_model(
        self,
        settings: ProviderSettings,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> BaseChatModel:
        """Create a :class:`ChatOpenAI` model from validated provider settings.

        Args:
            settings: The ``provider`` section of the application configuration.
            environ: Environment mapping used to resolve ``api_key_env``;
                defaults to ``os.environ``.

        Returns:
            A chat model bound to the configured endpoint, model and limits.

        Raises:
            ProviderConfigurationError: If the endpoint URL, the model name or
                the API key is missing.
        """
        api_key = settings.resolved_api_key(environ)
        if settings.base_url is None or settings.model is None or api_key is None:
            raise ProviderConfigurationError(
                f"cannot create the {PROVIDER_NAME} provider: "
                "provider.base_url, provider.model and an API key are required; "
                "fix the configuration or the API key environment variable"
            )
        return ChatOpenAI(
            model=settings.model,
            base_url=settings.base_url,
            api_key=api_key,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            timeout=settings.timeout_seconds,
            # Retries are a runtime decision: the SDK must not retry silently,
            # otherwise timeouts and errors are reported much later than the
            # configured timeout.
            max_retries=0,
        )
