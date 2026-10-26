"""Pre-start validation of the workspace and the model endpoint configuration.

The CLI runs these checks before any interface starts, so configuration
problems are reported with a fix suggestion instead of surfacing as a runtime
failure later.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from minimum_coding_agent.config.settings import ProviderSettings, Settings


@dataclass(frozen=True)
class StartupIssue:
    """A problem that prevents the application from starting.

    Attributes:
        field: Configuration field or resource related to the problem.
        message: Human-readable description of the problem.
        hint: Suggested action that may resolve the problem.
    """

    field: str
    message: str
    hint: str


class StartupValidationError(Exception):
    """Raised when one or more pre-start checks fail.

    Attributes:
        issues: The problems that were found.
    """

    def __init__(self, issues: Sequence[StartupIssue]) -> None:
        """Initialize the error.

        Args:
            issues: Non-empty sequence of problems found during validation.
        """
        self.issues = list(issues)
        super().__init__(self.format_message(self.issues))

    @staticmethod
    def format_message(issues: Sequence[StartupIssue]) -> str:
        """Format issues as a readable, multi-line error message.

        Args:
            issues: Problems found during validation.

        Returns:
            The formatted message, without any secret values.
        """
        lines = ["startup validation failed"]
        for issue in issues:
            lines.append(f"  - {issue.field}: {issue.message}")
            lines.append(f"    hint: {issue.hint}")
        return "\n".join(lines)


def validate_startup(
    settings: Settings,
    *,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Validate the workspace and model endpoint before the application starts.

    Args:
        settings: Merged application settings.
        environ: Environment mapping used to resolve ``provider.api_key_env``;
            defaults to ``os.environ``.

    Returns:
        Human-readable warnings that do not block startup.

    Raises:
        StartupValidationError: If the workspace or model endpoint configuration
            is unusable.
    """
    issues: list[StartupIssue] = []
    warnings: list[str] = []

    issues.extend(_check_workspace(settings.workspace))
    issues.extend(_check_provider(settings.provider, environ, warnings))

    if issues:
        raise StartupValidationError(issues)
    return warnings


def _check_workspace(workspace: Path) -> list[StartupIssue]:
    """Validate that the workspace exists, is a directory, and is writable.

    Args:
        workspace: Absolute workspace path.

    Returns:
        The problems found, if any.
    """
    issues: list[StartupIssue] = []
    if not workspace.exists():
        issues.append(
            StartupIssue(
                field="workspace",
                message=f"workspace directory does not exist: {workspace}",
                hint="create the directory or pass --workspace <dir>",
            )
        )
        return issues
    if not workspace.is_dir():
        issues.append(
            StartupIssue(
                field="workspace",
                message=f"workspace path is not a directory: {workspace}",
                hint="pass --workspace <dir> pointing to a directory",
            )
        )
        return issues
    if not os.access(workspace, os.W_OK):
        issues.append(
            StartupIssue(
                field="workspace",
                message=f"workspace directory is not writable: {workspace}",
                hint="fix the directory permissions or pass --workspace <dir>",
            )
        )
    return issues


def _check_provider(
    provider: ProviderSettings,
    environ: Mapping[str, str] | None,
    warnings: list[str],
) -> list[StartupIssue]:
    """Validate that the model endpoint configuration is complete.

    Args:
        provider: Provider configuration to validate.
        environ: Environment mapping used to resolve the API key variable.
        warnings: List that receives non-blocking warnings.

    Returns:
        The problems found, if any.
    """
    issues: list[StartupIssue] = []
    if provider.base_url is None:
        issues.append(
            StartupIssue(
                field="provider.base_url",
                message="model endpoint base URL is not configured",
                hint="set provider.base_url in the configuration file or MCA_BASE_URL",
            )
        )
    if provider.model is None:
        issues.append(
            StartupIssue(
                field="provider.model",
                message="model name is not configured",
                hint="set provider.model in the configuration file or MCA_MODEL",
            )
        )
    if provider.resolved_api_key(environ) is None:
        if provider.api_key_env is not None:
            issues.append(
                StartupIssue(
                    field="provider.api_key_env",
                    message=f"environment variable {provider.api_key_env} is not set",
                    hint=f"export {provider.api_key_env}=<key> or set provider.api_key",
                )
            )
        else:
            issues.append(
                StartupIssue(
                    field="provider.api_key",
                    message="no API key is configured",
                    hint="set provider.api_key_env (preferred) or provider.api_key",
                )
            )
    if provider.inline_secret_is_used():
        warnings.append(
            "provider.api_key is set inline; prefer provider.api_key_env "
            "to keep secrets out of configuration files"
        )
    return issues
