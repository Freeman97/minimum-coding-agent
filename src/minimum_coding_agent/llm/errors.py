"""Error types and classification for the model access layer.

Provider and registry errors are raised during startup or registration, while
:class:`ModelCallError` carries a classified, user-readable summary of a failed
streaming call. Error messages are sanitized before they reach logs, the
console or the user: API keys and authorization tokens never leak.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from enum import Enum

import openai
from pydantic import ValidationError

from minimum_coding_agent.config.settings import REDACTED

#: Maximum number of characters kept from the underlying exception message.
_MAX_DETAIL_CHARS = 300

#: Patterns that commonly carry credentials in third-party error messages.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{6,}"),
    re.compile(r"(?i)\b(?:authorization|api[_-]?key)\b\s*[:=]\s*\S+"),
)


class LlmError(Exception):
    """Base class for model layer errors that are safe to show to users.

    Attributes:
        message: Sanitized, user-readable description of the problem.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message: Sanitized, user-readable description of the problem.
        """
        super().__init__(message)
        self.message = message


class ProviderContractError(LlmError):
    """Raised when a provider does not satisfy the extension contract."""


class ProviderConfigurationError(LlmError):
    """Raised when a chat model cannot be created from the configuration."""


class DuplicateProviderError(LlmError):
    """Raised when a provider name is registered more than once."""

    def __init__(self, provider_name: str) -> None:
        """Initialize the error.

        Args:
            provider_name: The provider name that was registered twice.
        """
        super().__init__(f"model provider {provider_name!r} is already registered")


class UnknownProviderError(LlmError):
    """Raised when the configuration selects an unregistered provider."""

    def __init__(self, requested: str, available: Sequence[str]) -> None:
        """Initialize the error.

        Args:
            requested: Provider name read from ``provider.name``.
            available: Names of the currently registered providers.
        """
        names = ", ".join(sorted(available)) if available else "<none>"
        super().__init__(
            f"unknown model provider {requested!r}; available providers: {names}"
        )


class ModelCallCategory(str, Enum):
    """Classification of a failed streaming chat call."""

    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    NETWORK = "network"
    SERVER = "server"
    RATE_LIMIT = "rate_limit"
    INVALID_REQUEST = "invalid_request"
    RESPONSE = "response"
    UNKNOWN = "unknown"


class ModelCallError(LlmError):
    """A classified failure of a streaming chat call.

    Attributes:
        category: Classification of the failure.
        hint: Suggested action for the user.
        retryable: Whether an immediate retry may succeed without configuration
            changes.
        status_code: HTTP status code reported by the endpoint, if any.
        partial_text: Text that was already received before the failure.
    """

    def __init__(
        self,
        message: str,
        *,
        category: ModelCallCategory,
        hint: str,
        retryable: bool,
        status_code: int | None = None,
        partial_text: str = "",
    ) -> None:
        """Initialize the error.

        Args:
            message: Sanitized, user-readable description of the problem.
            category: Classification of the failure.
            hint: Suggested action for the user.
            retryable: Whether an immediate retry may succeed.
            status_code: HTTP status code reported by the endpoint, if any.
            partial_text: Text that was already received before the failure.
        """
        super().__init__(message)
        self.category = category
        self.hint = hint
        self.retryable = retryable
        self.status_code = status_code
        self.partial_text = partial_text


def redact_secret_text(text: str, *, secrets: Sequence[str] = ()) -> str:
    """Replace API keys and authorization tokens in ``text`` with a placeholder.

    Args:
        text: Text that may contain credentials.
        secrets: Known secret values that must be removed verbatim.

    Returns:
        The text with every known secret and common credential pattern replaced
        by :data:`~minimum_coding_agent.config.settings.REDACTED`.
    """
    redacted = text
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def classify_model_error(
    exc: BaseException,
    *,
    partial_text: str = "",
    secrets: Sequence[str] = (),
) -> ModelCallError:
    """Convert an exception raised by a chat model call into a classified error.

    The returned error is safe to show to the user: the underlying exception
    text is truncated and sanitized, and raw provider details are omitted for
    authentication failures because they may echo credentials.

    Args:
        exc: The exception raised by the provider or by LangChain.
        partial_text: Text already received from the stream before the failure.
        secrets: Known secret values that must not appear in the message.

    Returns:
        A :class:`ModelCallError` describing the failure and a recovery hint.
    """
    status_code = _status_code(exc)
    detail = redact_secret_text(_truncate(str(exc)), secrets=secrets)

    def make_error(
        message: str,
        *,
        category: ModelCallCategory,
        hint: str,
        retryable: bool,
        include_detail: bool = True,
    ) -> ModelCallError:
        if status_code is not None and category is not ModelCallCategory.RESPONSE:
            message = f"{message} (HTTP {status_code})"
        if include_detail and detail:
            message = f"{message}: {detail}"
        return ModelCallError(
            message,
            category=category,
            hint=hint,
            retryable=retryable,
            status_code=status_code,
            partial_text=partial_text,
        )

    if isinstance(exc, (openai.APITimeoutError, TimeoutError, asyncio.TimeoutError)):
        return make_error(
            "model request timed out",
            category=ModelCallCategory.TIMEOUT,
            hint="retry, or increase provider.timeout_seconds",
            retryable=True,
        )
    if isinstance(
        exc,
        (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
        ),
    ):
        return make_error(
            "model endpoint rejected the credentials",
            category=ModelCallCategory.AUTHENTICATION,
            hint="check provider.api_key_env and provider.base_url",
            retryable=False,
            include_detail=False,
        )
    if isinstance(exc, openai.APIConnectionError):
        return make_error(
            "cannot reach the model endpoint",
            category=ModelCallCategory.NETWORK,
            hint="check network connectivity and provider.base_url",
            retryable=True,
        )
    if isinstance(exc, openai.RateLimitError):
        return make_error(
            "model endpoint rate limit exceeded",
            category=ModelCallCategory.RATE_LIMIT,
            hint="wait before retrying",
            retryable=True,
        )
    if isinstance(exc, openai.InternalServerError) or (
        status_code is not None and status_code >= 500
    ):
        return make_error(
            "model endpoint failed with a server error",
            category=ModelCallCategory.SERVER,
            hint="retry later or check the endpoint status",
            retryable=True,
        )
    if isinstance(
        exc,
        (
            openai.BadRequestError,
            openai.UnprocessableEntityError,
            openai.NotFoundError,
        ),
    ) or (status_code is not None and 400 <= status_code < 500):
        return make_error(
            "model endpoint rejected the request",
            category=ModelCallCategory.INVALID_REQUEST,
            hint="check provider.model and the request parameters",
            retryable=False,
        )
    if isinstance(exc, (json.JSONDecodeError, ValidationError)):
        return make_error(
            "cannot parse the model response",
            category=ModelCallCategory.RESPONSE,
            hint="check that the endpoint is OpenAI-compatible, then retry",
            retryable=True,
        )
    return make_error(
        "unexpected error while calling the model",
        category=ModelCallCategory.UNKNOWN,
        hint="check the logs and retry",
        retryable=False,
    )


def _status_code(exc: BaseException) -> int | None:
    """Return the HTTP status code carried by an exception, if any.

    Args:
        exc: Exception raised by the model call.

    Returns:
        The integer status code, or ``None`` when the exception has none.
    """
    value = getattr(exc, "status_code", None)
    return value if isinstance(value, int) else None


def _truncate(text: str) -> str:
    """Shorten a potentially long exception message.

    Args:
        text: Original exception text.

    Returns:
        The text, truncated to ``_MAX_DETAIL_CHARS`` characters with an ellipsis.
    """
    if len(text) <= _MAX_DETAIL_CHARS:
        return text
    return text[: _MAX_DETAIL_CHARS - 3] + "..."
