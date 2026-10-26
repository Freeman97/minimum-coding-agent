"""Layered configuration loading (CLI arguments > environment > YAML > defaults)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from minimum_coding_agent.config.settings import Settings

#: Environment variable names understood by the loader, in priority order.
ENV_BASE_URL = "MCA_BASE_URL"
ENV_API_KEY = "MCA_API_KEY"
ENV_MODEL = "MCA_MODEL"
ENV_CONFIG = "MCA_CONFIG"
ENV_WORKSPACE = "MCA_WORKSPACE"

_ENV_TO_FIELD = {
    ENV_BASE_URL: "base_url",
    ENV_API_KEY: "api_key",
    ENV_MODEL: "model",
    ENV_CONFIG: "config",
    ENV_WORKSPACE: "workspace",
}


class ConfigLoadError(Exception):
    """Raised when a configuration file cannot be read, parsed or validated.

    Attributes:
        message: Human-readable description of the configuration problem.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message: Human-readable description of the configuration problem.
        """
        super().__init__(message)
        self.message = message


class _EnvironmentSettings(BaseModel):
    """Explicit ``MCA_*`` environment overrides.

    The mapping is deliberately explicit and self-contained: only the five
    documented ``MCA_*`` variables are read, and no other environment variable
    (for example a bare ``MODEL`` or ``WORKSPACE``) can leak into the settings.
    This keeps the loader hermetic and the test suite independent of ambient
    shell or CI variables.
    """

    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)

    base_url: str | None = None
    api_key: SecretStr | None = None
    model: str | None = None
    config: Path | None = None
    workspace: Path | None = None

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> _EnvironmentSettings:
        """Build the overrides from an environment mapping.

        Args:
            environ: Environment mapping to read; defaults to ``os.environ``.

        Returns:
            The parsed environment overrides.
        """
        source = os.environ if environ is None else environ
        values: dict[str, str] = {}
        for env_name, field_name in _ENV_TO_FIELD.items():
            value = source.get(env_name)
            if value:
                values[field_name] = value
        return cls.model_validate(values)


def load_settings(
    config_path: Path | str | None = None,
    *,
    workspace: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Load settings from defaults, a YAML file, environment variables and CLI arguments.

    Priority (highest first): CLI arguments, environment variables, YAML file,
    built-in defaults. Relative ``workspace`` paths are resolved against the
    current working directory.

    Args:
        config_path: Configuration file passed on the command line, if any.
        workspace: Workspace directory passed on the command line, if any.
        environ: Environment mapping to use instead of ``os.environ``.

    Returns:
        The merged, validated settings.

    Raises:
        ConfigLoadError: If the file cannot be read or parsed, or if the merged
            configuration fails validation.
    """
    environment = _EnvironmentSettings.from_environ(environ)

    selected_config = Path(config_path) if config_path is not None else environment.config
    file_data: dict[str, Any] = {}
    if selected_config is not None:
        file_data = _read_yaml_mapping(Path(selected_config))

    overrides: dict[str, Any] = {}
    provider_overrides: dict[str, Any] = {}
    if environment.base_url is not None:
        provider_overrides["base_url"] = environment.base_url
    if environment.api_key is not None:
        provider_overrides["api_key"] = environment.api_key
    if environment.model is not None:
        provider_overrides["model"] = environment.model
    if provider_overrides:
        overrides["provider"] = provider_overrides
    if environment.workspace is not None:
        overrides["workspace"] = environment.workspace
    if workspace is not None:
        overrides["workspace"] = workspace

    merged = _deep_merge(file_data, overrides)
    if environment.api_key is not None:
        # MCA_API_KEY has higher priority than the file, so it replaces a
        # provider.api_key_env reference instead of conflicting with it.
        provider_section = merged.get("provider")
        if isinstance(provider_section, dict):
            provider_section.pop("api_key_env", None)
    try:
        settings = Settings.model_validate(merged)
    except ValidationError as exc:
        raise ConfigLoadError(_format_validation_error(selected_config, exc)) from exc
    return _resolve_workspace(settings)


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    """Read a YAML configuration file and require a mapping at the top level.

    Args:
        path: Configuration file to read.

    Returns:
        The parsed mapping, or an empty mapping for an empty file.

    Raises:
        ConfigLoadError: If the file is missing, unreadable, invalid YAML, or
            does not contain a mapping.
    """
    if not path.exists():
        raise ConfigLoadError(f"configuration file not found: {path}")
    if path.is_dir():
        raise ConfigLoadError(f"configuration path is a directory, not a file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigLoadError(f"cannot read configuration file {path}: {exc.strerror}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        problem = getattr(exc, "problem", None) or "invalid YAML syntax"
        location = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        raise ConfigLoadError(
            f"configuration file {path} is not valid YAML{location}: {problem}"
        ) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigLoadError(
            f"configuration file {path} must contain a mapping at the top level"
        )
    return data


def _deep_merge(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overrides`` on top of ``base``.

    Args:
        base: Lower-priority mapping.
        overrides: Higher-priority mapping; lists replace base lists.

    Returns:
        A new merged mapping.
    """
    merged: dict[str, Any] = dict(base)
    for key, value in overrides.items():
        base_value = merged.get(key)
        if isinstance(base_value, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged


def _resolve_workspace(settings: Settings) -> Settings:
    """Resolve the workspace path against the current working directory.

    Args:
        settings: Validated settings with a possibly relative workspace.

    Returns:
        A copy of the settings whose workspace is absolute.
    """
    workspace = settings.workspace
    if not workspace.is_absolute():
        workspace = Path.cwd() / workspace
    return settings.model_copy(update={"workspace": workspace.resolve()})


def _format_validation_error(config_path: Path | None, exc: ValidationError) -> str:
    """Format a pydantic validation error without leaking secret values.

    Args:
        config_path: Configuration file being validated, if any.
        exc: The pydantic validation error.

    Returns:
        A multi-line, human-readable error description.
    """
    lines = ["configuration is invalid"]
    if config_path is not None:
        lines[0] = f"configuration is invalid ({config_path})"
    for error in exc.errors(include_url=False):
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        message = str(error["msg"]).removeprefix("Value error, ")
        lines.append(f"  - {location}: {message}")
    lines.append("hint: fix the listed fields in the configuration file or environment")
    return "\n".join(lines)
