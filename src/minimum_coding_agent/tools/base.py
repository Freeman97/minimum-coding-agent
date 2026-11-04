"""Toolset contract, shared context and the JSON result boundary."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from minimum_coding_agent.config.settings import REDACTED, Settings
from minimum_coding_agent.tools.errors import ToolError
from minimum_coding_agent.tools.workspace import WorkspaceGuard

ConfirmCommand = Callable[[str], Awaitable[bool]]
_LOGGER = logging.getLogger(__name__)
_SECRET_NAME = re.compile(
    r"API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|PRIVATE_?KEY|ACCESS_?KEY", re.I
)


class ToolArguments(BaseModel):
    """Reject unknown fields and coercion of model-supplied tool arguments."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


@dataclass(frozen=True)
class ToolContext:
    """Share configuration, guarded workspace and an optional async Bash prompt.

    Attributes:
        settings: Application configuration, including toolset limits.
        confirm_command: Async approval callback; absence means deny.
        environ: Environment snapshot, replaceable by tests and embedding callers.
        guard: Canonical workspace path guard shared by all filesystem tools.
    """

    settings: Settings = field(repr=False)
    confirm_command: ConfirmCommand | None = None
    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ), repr=False)
    guard: WorkspaceGuard = field(init=False)

    def __post_init__(self) -> None:
        """Pin the workspace and isolate the supplied environment mapping."""
        object.__setattr__(self, "guard", WorkspaceGuard(self.settings.workspace))
        object.__setattr__(self, "environ", dict(self.environ))

    def secret_env_names(self) -> set[str]:
        """Find credential variables that must not be inherited by Bash.

        Returns:
            Known credential names, including the configured provider key name.
        """
        names = {name for name in self.environ if _SECRET_NAME.search(name)}
        names.add("MCA_API_KEY")
        if self.settings.provider.api_key_env:
            names.add(self.settings.provider.api_key_env)
        for server in self.settings.mcp.servers:
            names.update(server.env)
        return names

    def redact(self, text: str) -> str:
        """Remove configured credential values from tool results.

        Args:
            text: Result or error text that may contain a known secret.

        Returns:
            Text with known credentials replaced by the project placeholder.
        """
        secrets = {self.environ.get(name, "") for name in self.secret_env_names()}
        secrets.add(self.settings.provider.resolved_api_key(self.environ) or "")
        for server in self.settings.mcp.servers:
            secrets.update(server.env.values())
        for secret in sorted(secrets - {""}, key=len, reverse=True):
            text = text.replace(secret, REDACTED)
        return text


@runtime_checkable
class Toolset(Protocol):
    """Build independently configurable LangChain tools from a shared context."""

    name: str

    def build(self, ctx: ToolContext) -> list[BaseTool]:
        """Build this toolset without starting an agent or a UI.

        Args:
            ctx: Configuration, workspace and confirmation callback.

        Returns:
            Tools with English descriptions and argument schemas.
        """
        ...


def error_result(error: ToolError, ctx: ToolContext) -> str:
    """Serialize a recoverable failure using the common JSON envelope.

    Args:
        error: Classified tool failure with a recovery hint.
        ctx: Context used to redact credential values.

    Returns:
        JSON text with ``ok=false`` and ``error.code/message/hint``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": error.code,
            "message": ctx.redact(error.message),
            "hint": ctx.redact(error.hint),
        },
    }
    if error.data is not None:
        result["data"] = _redact_data(error.data, ctx)
    return json.dumps(result, ensure_ascii=False)


def _failure(exc: Exception, ctx: ToolContext, name: str) -> str:
    """Classify failures without logging exception text or argument values."""
    if isinstance(exc, ToolError):
        return error_result(exc, ctx)
    if isinstance(exc, ValidationError):
        fields = ", ".join(".".join(map(str, item["loc"])) for item in exc.errors())
        error = ToolError(
            "INVALID_ARGUMENT",
            f"invalid tool arguments: {fields}",
            "Follow the tool argument schema.",
        )
    elif isinstance(exc, PermissionError):
        error = ToolError("PERMISSION_DENIED", "permission denied", "Check workspace permissions.")
    elif isinstance(exc, FileNotFoundError):
        error = ToolError("NOT_FOUND", "path does not exist", "Check the workspace-relative path.")
    elif isinstance(exc, FileExistsError):
        error = ToolError(
            "ALREADY_EXISTS", "target already exists", "Choose a new path or edit it."
        )
    elif isinstance(exc, OSError):
        error = ToolError(
            "IO_ERROR", "filesystem or process operation failed", "Check the path and OS."
        )
    else:
        _LOGGER.error("tool %s failed unexpectedly (%s)", name, type(exc).__name__)
        error = ToolError("INTERNAL_ERROR", "unexpected tool failure", "Check application logs.")
    return error_result(error, ctx)


def _success(data: Any, ctx: ToolContext) -> str:
    """Redact text values before encoding, keeping JSON valid for any secret."""
    return json.dumps({"ok": True, "data": _redact_data(data, ctx)}, ensure_ascii=False)


def _redact_data(data: Any, ctx: ToolContext) -> Any:
    """Redact only string values without altering JSON syntax or numeric values."""
    if isinstance(data, str):
        return ctx.redact(data)
    if isinstance(data, dict):
        return {key: _redact_data(value, ctx) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [_redact_data(value, ctx) for value in data]
    return data


class ResultTool(BaseTool):
    """Preserve a LangChain tool schema while converting failures to JSON text.

    LangChain creates a ``ToolMessage`` automatically when invoked with a full
    tool call, including its original ``tool_call_id``. Cancellation propagates.
    """

    wrapped: BaseTool = Field(exclude=True, repr=False)
    ctx: ToolContext = Field(exclude=True, repr=False)

    def _run(self, *args: Any, config: RunnableConfig, **kwargs: Any) -> str:
        """Execute a synchronous tool behind the common result boundary."""
        try:
            if isinstance(self.wrapped, StructuredTool) and self.wrapped.func is None:
                raise ToolError(
                    "ASYNC_REQUIRED", "tool is async-only", "Use await tool.ainvoke(...)."
                )
            data = self.wrapped.invoke(args[0] if args else kwargs, config=config)
            return _success(data, self.ctx)
        except Exception as exc:
            return _failure(exc, self.ctx, self.name)

    async def _arun(self, *args: Any, config: RunnableConfig, **kwargs: Any) -> str:
        """Execute an asynchronous tool and preserve task cancellation."""
        try:
            data = await self.wrapped.ainvoke(args[0] if args else kwargs, config=config)
            return _success(data, self.ctx)
        except Exception as exc:
            return _failure(exc, self.ctx, self.name)


def protect_tool(tool: BaseTool, ctx: ToolContext) -> BaseTool:
    """Wrap a tool with validation, exception handling and JSON result encoding.

    Args:
        tool: Tool returning JSON-serializable data or raising ``ToolError``.
        ctx: Context used to redact credential values.

    Returns:
        A LangChain-compatible tool with the same name, description and schema.
    """
    return ResultTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        wrapped=tool,
        ctx=ctx,
        handle_validation_error=lambda exc: _failure(exc, ctx, tool.name),
    )
