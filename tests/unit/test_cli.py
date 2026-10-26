"""Unit tests for the command line interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from minimum_coding_agent import __version__
from minimum_coding_agent.cli import ExitCode, main


def set_valid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCA_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("MCA_MODEL", "test-model")
    monkeypatch.setenv("MCA_API_KEY", "sk-test")


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert f"mca {__version__}" in capsys.readouterr().out


def test_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert "usage:" in output
    assert "run" in output
    assert "--workspace" in output
    assert "--config" in output


def test_unknown_option_is_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--unknown-option"])
    assert excinfo.value.code == int(ExitCode.USAGE_ERROR)
    assert "unrecognized arguments" in capsys.readouterr().err


def test_run_requires_task(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["run"])
    assert excinfo.value.code == int(ExitCode.USAGE_ERROR)
    assert "required" in capsys.readouterr().err


def test_missing_config_file_returns_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.yaml"
    code = main(["--config", str(missing)])
    assert code == int(ExitCode.CONFIG_ERROR)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "configuration file not found" in captured.err
    assert str(missing) in captured.err


def test_invalid_config_returns_config_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "agent.yaml"
    config.write_text("provider:\n  unknown_key: true\n", encoding="utf-8")
    code = main(["--config", str(config)])
    assert code == int(ExitCode.CONFIG_ERROR)
    assert "provider.unknown_key" in capsys.readouterr().err


def test_missing_endpoint_returns_startup_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--workspace", str(tmp_path)])
    assert code == int(ExitCode.STARTUP_ERROR)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "provider.base_url" in captured.err
    assert "provider.model" in captured.err
    assert "provider.api_key" in captured.err


def test_missing_workspace_returns_startup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    set_valid_environment(monkeypatch)
    missing = tmp_path / "missing"
    code = main(["--workspace", str(missing)])
    assert code == int(ExitCode.STARTUP_ERROR)
    assert str(missing) in capsys.readouterr().err


def test_interactive_placeholder_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    set_valid_environment(monkeypatch)
    code = main(["--workspace", str(tmp_path)])
    assert code == int(ExitCode.OK)
    captured = capsys.readouterr()
    assert "Interactive console is not available yet" in captured.out
    assert str(tmp_path) in captured.out
    assert "model: test-model" in captured.out
    assert "sk-test" not in captured.out + captured.err


def test_headless_placeholder_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    set_valid_environment(monkeypatch)
    code = main(["run", "fix the bug", "--workspace", str(tmp_path)])
    assert code == int(ExitCode.OK)
    output = capsys.readouterr().out
    assert "Headless run is not available yet" in output
    assert "Task: fix the bug" in output
    assert str(tmp_path) in output


def test_global_options_before_subcommand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    set_valid_environment(monkeypatch)
    code = main(["--workspace", str(tmp_path), "run", "prepare the task"])
    assert code == int(ExitCode.OK)
    assert "Task: prepare the task" in capsys.readouterr().out


def test_config_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "agent.yaml"
    config.write_text(
        "\n".join(
            [
                "provider:",
                "  base_url: https://file.example.com",
                "  model: file-model",
                "  api_key_env: TEAM_API_KEY",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MCA_CONFIG", str(config))
    monkeypatch.setenv("MCA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("TEAM_API_KEY", "sk-file")
    code = main([])
    assert code == int(ExitCode.OK)
    captured = capsys.readouterr()
    assert "model: file-model" in captured.out
    assert "warning:" not in captured.err


def test_bare_environment_variables_do_not_satisfy_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BASE_URL", "https://bare.example.com")
    monkeypatch.setenv("MODEL", "bare-model")
    monkeypatch.setenv("API_KEY", "sk-bare")
    code = main(["--workspace", str(tmp_path)])
    assert code == int(ExitCode.STARTUP_ERROR)
    error = capsys.readouterr().err
    assert "provider.base_url" in error
    assert "bare-model" not in error


def test_inline_api_key_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    set_valid_environment(monkeypatch)
    code = main(["--workspace", str(tmp_path)])
    assert code == int(ExitCode.OK)
    captured = capsys.readouterr()
    assert "warning: provider.api_key is set inline" in captured.err
    assert "sk-test" not in captured.err


def test_cli_workspace_overrides_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    set_valid_environment(monkeypatch)
    environment_workspace = tmp_path / "env-workspace"
    cli_workspace = tmp_path / "cli-workspace"
    environment_workspace.mkdir()
    cli_workspace.mkdir()
    monkeypatch.setenv("MCA_WORKSPACE", str(environment_workspace))
    code = main(["--workspace", str(cli_workspace)])
    assert code == int(ExitCode.OK)
    output = capsys.readouterr().out
    assert str(cli_workspace) in output
    assert str(environment_workspace) not in output
