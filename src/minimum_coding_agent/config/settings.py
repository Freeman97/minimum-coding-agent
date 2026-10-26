"""Pydantic settings models for the minimum coding agent.

The models are intentionally strict: unknown keys are rejected, so configuration
typos surface before the application starts. Secrets use :class:`pydantic.SecretStr`
and are masked by :meth:`Settings.redacted_dict`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

#: Placeholder used instead of secret values in logs and error reports.
REDACTED = "***REDACTED***"

#: Directory names skipped by the workspace tools by default.
DEFAULT_EXCLUDED_DIRS: tuple[str, ...] = (
    ".git",
    ".venv",
    ".tools",
    ".uv-cache",
    ".uv-python",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
)


class SettingsModel(BaseModel):
    """Base class for configuration sections with strict validation."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ProviderSettings(SettingsModel):
    """Configuration of the OpenAI-compatible model endpoint."""

    name: str = Field(default="openai-compatible", min_length=1)
    base_url: str | None = Field(default=None, min_length=1)
    api_key: SecretStr | None = None
    api_key_env: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float = Field(default=60.0, gt=0.0)

    @model_validator(mode="after")
    def _validate_credentials(self) -> ProviderSettings:
        """Reject configurations that mix inline and environment credentials.

        Returns:
            The validated provider settings.

        Raises:
            ValueError: If both ``api_key`` and ``api_key_env`` are configured.
        """
        if self.api_key is not None and self.api_key_env is not None:
            msg = "provider.api_key and provider.api_key_env are mutually exclusive"
            raise ValueError(msg)
        return self

    def resolved_api_key(self, environ: Mapping[str, str] | None = None) -> str | None:
        """Resolve the API key from the inline secret or the configured environment variable.

        Args:
            environ: Optional environment mapping; defaults to ``os.environ``.

        Returns:
            The API key, or ``None`` when no key is configured.
        """
        if self.api_key is not None:
            return self.api_key.get_secret_value()
        if self.api_key_env is None:
            return None
        environment = os.environ if environ is None else environ
        return environment.get(self.api_key_env) or None

    def inline_secret_is_used(self) -> bool:
        """Report whether the inline ``api_key`` is configured.

        Returns:
            ``True`` when an inline secret is present, ``False`` otherwise.
        """
        return self.api_key is not None


class ContextSettings(SettingsModel):
    """Context compression budget for the agent runtime."""

    max_tokens: int = Field(default=64000, ge=1000)
    llm_summary_threshold_tokens: int = Field(default=48000, ge=1000)
    compressors: list[str] = Field(default_factory=list)


class AgentSettings(SettingsModel):
    """Agent runtime configuration."""

    max_iterations: int = Field(default=30, ge=1)
    context: ContextSettings = Field(default_factory=ContextSettings)


class FilesystemSettings(SettingsModel):
    """Configuration of the filesystem toolset."""

    enabled: bool = True
    max_depth: int = Field(default=3, ge=1, le=32)
    max_entries: int = Field(default=2000, ge=1)
    exclude_dirs: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDED_DIRS))


class EditorSettings(SettingsModel):
    """Configuration of the text editor toolset."""

    enabled: bool = True


class BashSettings(SettingsModel):
    """Configuration of the shell command toolset."""

    enabled: bool = True
    timeout_seconds: float = Field(default=120.0, gt=0.0)
    max_output_chars: int = Field(default=20000, ge=1000)
    confirm_dangerous_commands: bool = True


class TodoSettings(SettingsModel):
    """Configuration of the TODO toolset."""

    enabled: bool = True


class SearchSettings(SettingsModel):
    """Configuration of the text search toolset."""

    enabled: bool = True
    max_results: int = Field(default=50, ge=1, le=1000)
    max_file_size_kb: int = Field(default=1024, ge=1)
    exclude_dirs: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDED_DIRS))


class CodeSettings(SettingsModel):
    """Configuration of the code intelligence toolset."""

    enabled: bool = True


class ToolsSettings(SettingsModel):
    """Configuration of every built-in toolset."""

    filesystem: FilesystemSettings = Field(default_factory=FilesystemSettings)
    editor: EditorSettings = Field(default_factory=EditorSettings)
    bash: BashSettings = Field(default_factory=BashSettings)
    todo: TodoSettings = Field(default_factory=TodoSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    code: CodeSettings = Field(default_factory=CodeSettings)


class McpServerSettings(SettingsModel):
    """Configuration of a single MCP server."""

    name: str = Field(min_length=1)
    transport: str = Field(default="stdio", min_length=1)
    command: str | None = Field(default=None, min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class McpSettings(SettingsModel):
    """Configuration of the MCP integration."""

    servers: list[McpServerSettings] = Field(default_factory=list)


class Settings(SettingsModel):
    """Root configuration of the application."""

    provider: ProviderSettings = Field(default_factory=ProviderSettings)
    workspace: Path = Field(default=Path("."))
    instructions_file: str = Field(default="AGENT.md", min_length=1)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    tools: ToolsSettings = Field(default_factory=ToolsSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)

    def redacted_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible copy of the settings with secrets masked.

        Returns:
            A mapping that is safe to print in logs and error messages.
        """
        data: dict[str, Any] = self.model_dump(mode="json")
        provider = data.get("provider")
        if isinstance(provider, dict) and self.provider.api_key is not None:
            provider["api_key"] = REDACTED
        return data
