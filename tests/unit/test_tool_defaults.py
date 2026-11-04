"""Configuration-driven built-in tool availability and editor limit validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from minimum_coding_agent.config.loader import load_settings
from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.tools.defaults import create_tool_registry


def test_default_registry_exposes_only_delivered_toolsets(tmp_path: Path) -> None:
    registry = create_tool_registry(Settings(workspace=tmp_path), environ={})
    assert registry.names() == (
        "create",
        "glob_files",
        "insert",
        "run_command",
        "str_replace",
        "tree",
        "view",
    )


@pytest.mark.parametrize(
    ("disabled", "missing"),
    [
        ("filesystem", {"tree", "glob_files"}),
        ("editor", {"view", "create", "str_replace", "insert"}),
        ("bash", {"run_command"}),
    ],
)
def test_disabled_toolsets_are_not_exposed(
    tmp_path: Path, disabled: str, missing: set[str]
) -> None:
    settings = Settings(workspace=tmp_path, tools={disabled: {"enabled": False}})
    names = set(create_tool_registry(settings, environ={}).names())
    assert not names.intersection(missing)
    assert names | missing == set(
        create_tool_registry(Settings(workspace=tmp_path), environ={}).names()
    )


def test_all_delivered_toolsets_can_be_disabled(tmp_path: Path) -> None:
    settings = Settings(
        workspace=tmp_path,
        tools={name: {"enabled": False} for name in ("filesystem", "editor", "bash")},
    )
    assert create_tool_registry(settings, environ={}).tools() == []


def test_editor_limits_defaults_and_example_config() -> None:
    settings = Settings()
    assert settings.tools.editor.max_file_size_kb == 1024
    assert settings.tools.editor.max_output_chars == 20000
    example = Path(__file__).resolve().parents[2] / "config/agent.example.yaml"
    loaded = load_settings(config_path=example, environ={})
    assert loaded.tools.editor == settings.tools.editor


@pytest.mark.parametrize(
    "options", [{"max_file_size_kb": 0}, {"max_output_chars": 999}, {"unknown": 1}]
)
def test_editor_limits_reject_invalid_config(options: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Settings(tools={"editor": options})
