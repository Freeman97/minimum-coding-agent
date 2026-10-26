"""Unit tests for pre-start validation."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.config.validation import (
    StartupValidationError,
    validate_startup,
)


def make_settings(
    workspace: Path,
    *,
    base_url: str | None = "https://api.example.com",
    model: str | None = "test-model",
    api_key_env: str | None = "TEAM_API_KEY",
    api_key: str | None = None,
) -> Settings:
    provider: dict[str, object] = {}
    if base_url is not None:
        provider["base_url"] = base_url
    if model is not None:
        provider["model"] = model
    if api_key_env is not None:
        provider["api_key_env"] = api_key_env
    if api_key is not None:
        provider["api_key"] = api_key
    return Settings.model_validate({"workspace": str(workspace), "provider": provider})


def test_valid_configuration_passes(tmp_path: Path) -> None:
    warnings = validate_startup(make_settings(tmp_path), environ={"TEAM_API_KEY": "sk-test"})
    assert warnings == []


def test_missing_workspace_is_reported(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(StartupValidationError) as excinfo:
        validate_startup(make_settings(missing), environ={"TEAM_API_KEY": "sk-test"})
    message = str(excinfo.value)
    assert "startup validation failed" in message
    assert "workspace" in message
    assert str(missing) in message
    assert "create the directory" in message


def test_workspace_file_is_rejected(tmp_path: Path) -> None:
    workspace_file = tmp_path / "workspace.txt"
    workspace_file.write_text("not a directory", encoding="utf-8")
    with pytest.raises(StartupValidationError, match="not a directory"):
        validate_startup(make_settings(workspace_file), environ={"TEAM_API_KEY": "sk-test"})


def test_read_only_workspace_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "read-only"
    workspace.mkdir()
    workspace.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        if os.access(workspace, os.W_OK):
            pytest.skip("current user bypasses directory permissions")
        with pytest.raises(StartupValidationError, match="not writable"):
            validate_startup(
                make_settings(workspace),
                environ={"TEAM_API_KEY": "sk-test"},
            )
    finally:
        workspace.chmod(stat.S_IRWXU)


@pytest.mark.parametrize(
    ("missing_field", "expected"),
    [
        ("base_url", "provider.base_url"),
        ("model", "provider.model"),
    ],
)
def test_missing_endpoint_fields_are_reported(
    tmp_path: Path, missing_field: str, expected: str
) -> None:
    kwargs: dict[str, object] = {"api_key_env": "TEAM_API_KEY"}
    kwargs[missing_field] = None
    settings = make_settings(tmp_path, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(StartupValidationError) as excinfo:
        validate_startup(settings, environ={"TEAM_API_KEY": "sk-test"})
    assert expected in str(excinfo.value)


def test_missing_api_key_is_reported(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, api_key_env=None)
    with pytest.raises(StartupValidationError) as excinfo:
        validate_startup(settings, environ={})
    message = str(excinfo.value)
    assert "provider.api_key" in message
    assert "no API key" in message


def test_missing_api_key_environment_variable_names_variable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, api_key_env="UNSET_TEST_KEY")
    with pytest.raises(StartupValidationError) as excinfo:
        validate_startup(settings, environ={})
    message = str(excinfo.value)
    assert "provider.api_key_env" in message
    assert "UNSET_TEST_KEY" in message
    assert "export UNSET_TEST_KEY" in message


def test_inline_api_key_produces_warning(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, api_key="sk-inline", api_key_env=None)
    warnings = validate_startup(settings, environ={})
    assert len(warnings) == 1
    assert "provider.api_key is set inline" in warnings[0]
    assert "sk-inline" not in warnings[0]


def test_multiple_issues_are_aggregated(tmp_path: Path) -> None:
    settings = Settings.model_validate({"workspace": str(tmp_path / "missing")})
    with pytest.raises(StartupValidationError) as excinfo:
        validate_startup(settings, environ={})
    issues = excinfo.value.issues
    fields = {issue.field for issue in issues}
    assert {"workspace", "provider.base_url", "provider.model", "provider.api_key"} <= fields
    message = str(excinfo.value)
    assert "hint:" in message


def test_error_message_does_not_leak_inline_secret(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, base_url=None, api_key="sk-top-secret", api_key_env=None)
    with pytest.raises(StartupValidationError) as excinfo:
        validate_startup(settings, environ={})
    message = str(excinfo.value)
    assert "sk-top-secret" not in message
    assert "provider.base_url" in message
