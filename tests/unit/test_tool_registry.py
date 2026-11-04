"""Toolset registration, schema exposure and recoverable execution failures."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.tools.base import ToolArguments, ToolContext, Toolset
from minimum_coding_agent.tools.errors import ToolError, ToolRegistrationError
from minimum_coding_agent.tools.registry import ToolRegistry


class EchoArguments(ToolArguments):
    text: str = Field(description="Text to return.")


@tool(args_schema=EchoArguments)
def echo(text: str) -> dict[str, str]:
    """Return the supplied text."""
    return {"text": text}


class StubToolset:
    name = "stub"

    def __init__(self, tools: list[BaseTool] | None = None, *, name: str = "stub") -> None:
        self.name = name
        self._tools = [echo] if tools is None else tools
        self.built = False

    def build(self, ctx: ToolContext) -> list[BaseTool]:
        self.built = True
        return self._tools


def make_registry(tmp_path: Path) -> ToolRegistry:
    return ToolRegistry(ToolContext(Settings(workspace=tmp_path), environ={}))


def test_toolset_contract_registration_and_schema(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    toolset = StubToolset()
    assert isinstance(toolset, Toolset)
    registry.register(toolset)
    assert registry.names() == ("echo",)
    exposed = convert_to_openai_tool(registry.tools()[0])["function"]
    assert exposed["name"] == "echo"
    assert exposed["description"] == "Return the supplied text."
    assert exposed["parameters"]["properties"]["text"]["type"] == "string"
    assert exposed["parameters"]["required"] == ["text"]
    assert json.loads(registry.get("echo").invoke({"text": "hello"})) == {
        "ok": True,
        "data": {"text": "hello"},
    }


def test_disabled_toolset_is_not_built_or_exposed(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    disabled = StubToolset(name="disabled")
    registry.register(disabled, enabled=False)
    registry.register(StubToolset())
    assert not disabled.built
    assert registry.names() == ("echo",)


def test_duplicate_names_reject_whole_registration(tmp_path: Path) -> None:
    @tool
    def other() -> str:
        """Return another value."""
        return "other"

    registry = make_registry(tmp_path)
    registry.register(StubToolset())
    with pytest.raises(ToolRegistrationError, match="echo"):
        registry.register(StubToolset([other, echo], name="conflicting"))
    assert registry.names() == ("echo",)
    with pytest.raises(ToolRegistrationError, match="stub"):
        registry.register(StubToolset())
    with pytest.raises(ToolRegistrationError, match="echo"):
        make_registry(tmp_path).register(StubToolset([echo, echo]))


@pytest.mark.parametrize("invalid", [object(), None, "not-a-toolset"])
def test_invalid_toolset_rejected(tmp_path: Path, invalid: object) -> None:
    with pytest.raises(ToolRegistrationError, match="toolset"):
        make_registry(tmp_path).register(invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize("arguments", [{}, {"text": 3}, {"text": "hi", "unknown": 1}])
def test_argument_errors_are_json_results(tmp_path: Path, arguments: dict[str, object]) -> None:
    registry = make_registry(tmp_path)
    registry.register(StubToolset())
    result = json.loads(registry.get("echo").invoke(arguments))
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert result["error"]["hint"]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ToolError("EXPECTED", "bad request", "try again"), "EXPECTED"),
        (PermissionError("no permission"), "PERMISSION_DENIED"),
        (FileNotFoundError("missing"), "NOT_FOUND"),
        (FileExistsError("existing"), "ALREADY_EXISTS"),
        (OSError("IO error"), "IO_ERROR"),
        (RuntimeError("private details"), "INTERNAL_ERROR"),
        (TypeError("bad result"), "INTERNAL_ERROR"),
    ],
)
def test_tool_exceptions_return_structured_errors(
    tmp_path: Path, error: Exception, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    @tool
    def failing() -> str:
        """Simulate a failed operation."""
        raise error

    registry = make_registry(tmp_path)
    registry.register(StubToolset([failing]))
    with caplog.at_level(logging.ERROR):
        result = json.loads(registry.get("failing").invoke({}))
    assert result["ok"] is False
    assert result["error"]["code"] == code
    assert "private details" not in caplog.text
    if code == "INTERNAL_ERROR":
        assert "failed unexpectedly" in caplog.text


def test_tool_call_returns_tool_message_with_original_id(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    registry.register(StubToolset())
    result = registry.get("echo").invoke(
        {"type": "tool_call", "id": "call-7", "name": "echo", "args": {"text": "hello"}}
    )
    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "call-7"
    assert json.loads(result.content)["data"] == {"text": "hello"}


@pytest.mark.asyncio
async def test_async_tool_results_errors_and_cancellation(tmp_path: Path) -> None:
    @tool
    async def async_echo(text: str) -> str:
        """Return a value or propagate cancellation."""
        if text == "cancel":
            raise asyncio.CancelledError
        if text == "fail":
            raise RuntimeError("private failure")
        return text

    registry = make_registry(tmp_path)
    registry.register(StubToolset([async_echo]))
    bound = registry.get("async_echo")
    assert json.loads(await bound.ainvoke({"text": "hello"}))["data"] == "hello"
    assert json.loads(await bound.ainvoke({"text": "fail"}))["ok"] is False
    assert json.loads(await bound.ainvoke({}))["error"]["code"] == "INVALID_ARGUMENT"
    assert json.loads(bound.invoke({"text": "hello"}))["error"]["code"] == "ASYNC_REQUIRED"
    with pytest.raises(asyncio.CancelledError):
        await bound.ainvoke({"text": "cancel"})


def test_secrets_are_redacted_without_breaking_json(tmp_path: Path) -> None:
    secret = 'secret"with\nnewlines'
    settings = Settings(workspace=tmp_path, provider={"api_key_env": "CUSTOM_CREDENTIAL"})
    ctx = ToolContext(settings, environ={"CUSTOM_CREDENTIAL": secret})
    registry = ToolRegistry(ctx)
    registry.register(StubToolset())
    result = registry.get("echo").invoke({"text": secret})
    assert json.loads(result)["data"]["text"] == "***REDACTED***"
    assert "secret" not in result
    assert secret not in repr(ctx)


def test_nonserializable_result_is_caught(tmp_path: Path) -> None:
    @tool
    def invalid_data() -> object:
        """Return data that cannot be sent to a model."""
        return object()

    registry = make_registry(tmp_path)
    registry.register(StubToolset([invalid_data]))
    assert json.loads(registry.get("invalid_data").invoke({}))["error"]["code"] == "INTERNAL_ERROR"
