"""Unit tests for model call error classification and secret redaction."""

from __future__ import annotations

import json

import httpx
import openai
import pytest
from pydantic import BaseModel, ValidationError

from minimum_coding_agent.config.settings import REDACTED
from minimum_coding_agent.llm.errors import (
    ModelCallCategory,
    ModelCallError,
    classify_model_error,
    redact_secret_text,
)

_SECRET = "sk-test-secret-1234567890"
_TOKEN = "tok_abcdef1234567890"
_ENDPOINT = "https://example.test/v1/chat/completions"


class _Payload(BaseModel):
    """Minimal model used to produce a pydantic validation error."""

    value: int


def _request() -> httpx.Request:
    return httpx.Request("POST", _ENDPOINT)


def _status_error(
    error_type: type[openai.APIStatusError],
    status_code: int,
    message: str,
) -> openai.APIStatusError:
    response = httpx.Response(
        status_code,
        request=_request(),
        json={"error": {"message": message}},
    )
    return error_type(message, response=response, body=None)


def test_authentication_error_is_not_retryable_and_hides_provider_detail() -> None:
    exc = _status_error(openai.AuthenticationError, 401, f"invalid key {_SECRET}")

    error = classify_model_error(exc)

    assert error.category is ModelCallCategory.AUTHENTICATION
    assert error.status_code == 401
    assert error.retryable is False
    assert "api_key_env" in error.hint
    assert _SECRET not in error.message
    assert "invalid key" not in error.message
    assert "HTTP 401" in error.message


def test_permission_denied_is_classified_as_authentication() -> None:
    exc = _status_error(openai.PermissionDeniedError, 403, "not allowed")

    error = classify_model_error(exc)

    assert error.category is ModelCallCategory.AUTHENTICATION
    assert error.status_code == 403
    assert error.retryable is False


def test_openai_timeout_is_retryable() -> None:
    exc = openai.APITimeoutError(request=_request())

    error = classify_model_error(exc)

    assert error.category is ModelCallCategory.TIMEOUT
    assert error.retryable is True
    assert error.status_code is None
    assert "retry" in error.hint


def test_builtin_timeout_is_retryable() -> None:
    error = classify_model_error(TimeoutError("request timed out"))

    assert error.category is ModelCallCategory.TIMEOUT
    assert error.retryable is True
    assert "timed out" in error.message


def test_server_error_is_retryable() -> None:
    exc = _status_error(openai.InternalServerError, 503, "upstream unavailable")

    error = classify_model_error(exc)

    assert error.category is ModelCallCategory.SERVER
    assert error.status_code == 503
    assert error.retryable is True
    assert "upstream unavailable" in error.message


def test_generic_exception_with_5xx_status_is_server_error() -> None:
    class _FakeStatusError(Exception):
        status_code = 502

    error = classify_model_error(_FakeStatusError("bad gateway from proxy"))

    assert error.category is ModelCallCategory.SERVER
    assert error.status_code == 502
    assert error.retryable is True


def test_rate_limit_is_retryable() -> None:
    exc = _status_error(openai.RateLimitError, 429, "slow down")

    error = classify_model_error(exc)

    assert error.category is ModelCallCategory.RATE_LIMIT
    assert error.status_code == 429
    assert error.retryable is True


def test_connection_error_is_network_category() -> None:
    exc = openai.APIConnectionError(request=_request())

    error = classify_model_error(exc)

    assert error.category is ModelCallCategory.NETWORK
    assert error.retryable is True


def test_invalid_request_is_not_retryable() -> None:
    exc = _status_error(openai.BadRequestError, 400, "unknown model")

    error = classify_model_error(exc)

    assert error.category is ModelCallCategory.INVALID_REQUEST
    assert error.status_code == 400
    assert error.retryable is False


def test_json_decode_error_is_response_category() -> None:
    exc = json.JSONDecodeError("Expecting value", "not json", 0)

    error = classify_model_error(exc)

    assert error.category is ModelCallCategory.RESPONSE
    assert error.retryable is True
    assert "parse" in error.message


def test_validation_error_is_response_category() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _Payload.model_validate({"value": "not a number"})

    error = classify_model_error(exc_info.value)

    assert error.category is ModelCallCategory.RESPONSE
    assert error.retryable is True


def test_arbitrary_exception_text_is_sanitized() -> None:
    exc = RuntimeError(f"request failed with api_key={_SECRET}")

    error = classify_model_error(exc)

    assert error.category is ModelCallCategory.UNKNOWN
    assert error.retryable is False
    assert _SECRET not in error.message
    assert REDACTED in error.message
    assert "unexpected error" in error.message


def test_known_secret_values_are_redacted() -> None:
    exc = RuntimeError("token super-secret-value was rejected")

    error = classify_model_error(exc, secrets=["super-secret-value"])

    assert "super-secret-value" not in error.message
    assert REDACTED in error.message


def test_partial_text_round_trips_on_the_classified_error() -> None:
    error = classify_model_error(TimeoutError("timed out"), partial_text="partial answer")

    assert error.partial_text == "partial answer"
    assert error.message == str(error)


def test_classified_error_keeps_status_and_sanitized_detail() -> None:
    exc = _status_error(
        openai.InternalServerError, 500, f"crashed while using {_SECRET}"
    )

    error = classify_model_error(exc)

    assert error.status_code == 500
    assert _SECRET not in error.message
    assert REDACTED in error.message


def test_redact_secret_text_redacts_common_credentials() -> None:
    text = f"key {_SECRET}, api_key={_SECRET}, Authorization: Bearer {_TOKEN}"

    redacted = redact_secret_text(text)

    assert _SECRET not in redacted
    assert _TOKEN not in redacted
    assert REDACTED in redacted


def test_redact_secret_text_leaves_plain_text_untouched() -> None:
    assert redact_secret_text("connection reset by peer") == "connection reset by peer"


def test_redact_secret_text_replaces_longer_known_secrets_first() -> None:
    redacted = redact_secret_text("token abcdef", secrets=["abc", "abcdef"])

    assert redacted == f"token {REDACTED}"


def test_model_call_error_exposes_classification_fields() -> None:
    error = ModelCallError(
        "model request timed out",
        category=ModelCallCategory.TIMEOUT,
        hint="retry",
        retryable=True,
        partial_text="half",
    )

    assert isinstance(error, ModelCallError)
    assert error.category is ModelCallCategory.TIMEOUT
    assert error.hint == "retry"
    assert error.retryable is True
    assert error.status_code is None
    assert error.partial_text == "half"
    assert str(error) == "model request timed out"
