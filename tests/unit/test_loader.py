"""Unit tests for layered configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from minimum_coding_agent.config.loader import ConfigLoadError, load_settings


def write_config(tmp_path: Path, text: str, name: str = "agent.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_are_used_without_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = load_settings(environ={})
    assert settings.workspace == tmp_path.resolve()
    assert settings.provider.base_url is None
    assert settings.agent.max_iterations == 30


def test_yaml_values_are_loaded(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        "\n".join(
            [
                "provider:",
                "  base_url: https://api.example.com",
                "  model: test-model",
                "  temperature: 0.3",
                "agent:",
                "  max_iterations: 7",
                "tools:",
                "  bash:",
                "    timeout_seconds: 5",
            ]
        ),
    )
    settings = load_settings(path, environ={})
    assert settings.provider.base_url == "https://api.example.com"
    assert settings.provider.model == "test-model"
    assert settings.provider.temperature == 0.3
    assert settings.agent.max_iterations == 7
    assert settings.tools.bash.timeout_seconds == 5.0


def test_empty_file_uses_defaults(tmp_path: Path) -> None:
    path = write_config(tmp_path, "# only comments\n")
    settings = load_settings(path, environ={})
    assert settings.provider.name == "openai-compatible"


def test_environment_overrides_file(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        "provider:\n  base_url: https://file.example.com\n  model: file-model\n",
    )
    settings = load_settings(
        path,
        environ={
            "MCA_BASE_URL": "https://env.example.com",
            "MCA_MODEL": "env-model",
        },
    )
    assert settings.provider.base_url == "https://env.example.com"
    assert settings.provider.model == "env-model"


def test_environment_api_key_is_masked(tmp_path: Path) -> None:
    settings = load_settings(environ={"MCA_API_KEY": "sk-env-secret"})
    assert settings.provider.resolved_api_key(environ={}) == "sk-env-secret"
    assert "sk-env-secret" not in str(settings.redacted_dict())


def test_empty_environment_values_are_ignored(tmp_path: Path) -> None:
    path = write_config(tmp_path, "provider:\n  base_url: https://file.example.com\n")
    settings = load_settings(path, environ={"MCA_BASE_URL": ""})
    assert settings.provider.base_url == "https://file.example.com"


def test_cli_workspace_overrides_environment_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    path = write_config(
        tmp_path,
        "workspace: file-ws\nprovider:\n  base_url: https://file.example.com\n",
    )
    settings = load_settings(
        path,
        workspace=tmp_path / "cli-ws",
        environ={"MCA_WORKSPACE": str(tmp_path / "env-ws")},
    )
    assert settings.workspace == (tmp_path / "cli-ws").resolve()


def test_relative_workspace_is_resolved_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "project"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    path = write_config(tmp_path, "workspace: relative-workspace\n")
    settings = load_settings(path, environ={})
    assert settings.workspace == (workdir / "relative-workspace").resolve()


def test_config_path_from_environment(tmp_path: Path) -> None:
    path = write_config(tmp_path, "provider:\n  model: env-config-model\n")
    settings = load_settings(environ={"MCA_CONFIG": str(path)})
    assert settings.provider.model == "env-config-model"


def test_cli_config_path_beats_environment(tmp_path: Path) -> None:
    env_config = write_config(tmp_path, "provider:\n  model: from-env\n", name="env.yaml")
    cli_config = write_config(tmp_path, "provider:\n  model: from-cli\n", name="cli.yaml")
    settings = load_settings(cli_config, environ={"MCA_CONFIG": str(env_config)})
    assert settings.provider.model == "from-cli"


def test_environment_api_key_overrides_file_api_key_env(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        "provider:\n  api_key_env: FILE_API_KEY\n  model: test-model\n",
    )
    settings = load_settings(path, environ={"MCA_API_KEY": "sk-env-secret"})
    assert settings.provider.api_key_env is None
    assert settings.provider.resolved_api_key(environ={}) == "sk-env-secret"


def test_missing_config_file_is_reported(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(ConfigLoadError) as excinfo:
        load_settings(missing, environ={})
    message = str(excinfo.value)
    assert "configuration file not found" in message
    assert str(missing) in message


def test_config_path_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigLoadError, match="not a file"):
        load_settings(tmp_path, environ={})


def test_invalid_yaml_is_reported_with_location(tmp_path: Path) -> None:
    path = write_config(tmp_path, "provider:\n  base_url: [unterminated\n")
    with pytest.raises(ConfigLoadError) as excinfo:
        load_settings(path, environ={})
    message = str(excinfo.value)
    assert "not valid YAML" in message
    assert "line" in message
    assert str(path) in message


def test_yaml_top_level_must_be_mapping(tmp_path: Path) -> None:
    path = write_config(tmp_path, "- first\n- second\n")
    with pytest.raises(ConfigLoadError, match="mapping"):
        load_settings(path, environ={})


def test_unknown_field_is_reported_with_path(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        "provider:\n  base_url: https://api.example.com\n  unknown_key: value\n",
    )
    with pytest.raises(ConfigLoadError) as excinfo:
        load_settings(path, environ={})
    message = str(excinfo.value)
    assert "provider.unknown_key" in message
    assert "Extra inputs are not permitted" in message
    assert str(path) in message


def test_invalid_type_is_reported_with_field(tmp_path: Path) -> None:
    path = write_config(tmp_path, "provider:\n  temperature: hot\n")
    with pytest.raises(ConfigLoadError) as excinfo:
        load_settings(path, environ={})
    message = str(excinfo.value)
    assert "provider.temperature" in message
    assert str(path) in message


def test_validation_error_does_not_leak_secret(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        "provider:\n  api_key: sk-file-secret\n  temperature: 5\n",
    )
    with pytest.raises(ConfigLoadError) as excinfo:
        load_settings(path, environ={})
    message = str(excinfo.value)
    assert "sk-file-secret" not in message
    assert "provider.temperature" in message


def test_example_configuration_is_valid() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    example = repo_root / "config" / "agent.example.yaml"
    settings = load_settings(example, environ={})
    assert settings.provider.base_url == "https://api.deepseek.com"
    assert settings.provider.model == "deepseek-chat"
    assert settings.provider.api_key is None
    assert settings.provider.api_key_env == "DEEPSEEK_API_KEY"
    assert "sk-" not in example.read_text(encoding="utf-8")
