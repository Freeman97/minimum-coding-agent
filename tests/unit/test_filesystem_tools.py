"""Directory expansion, root-relative glob semantics and traversal boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.tools.base import ToolContext
from minimum_coding_agent.tools.filesystem import FilesystemToolset
from minimum_coding_agent.tools.registry import ToolRegistry


def registry_for(workspace: Path, **options: Any) -> ToolRegistry:
    settings = Settings(workspace=workspace, tools={"filesystem": options})
    registry = ToolRegistry(ToolContext(settings, environ={}))
    registry.register(FilesystemToolset())
    return registry


def sample_tree(tmp_path: Path) -> None:
    (tmp_path / "top.py").write_text("top", encoding="utf-8")
    (tmp_path / "src/deep").mkdir(parents=True)
    (tmp_path / "src/main.py").write_text("main", encoding="utf-8")
    (tmp_path / "src/deep/extra.py").write_text("extra", encoding="utf-8")
    (tmp_path / "src/note.md").write_text("note", encoding="utf-8")
    for name in (".git", ".venv", "node_modules"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "hidden.py").write_text("hidden", encoding="utf-8")


def test_tree_recursive_types_exclusions_and_depth(tmp_path: Path) -> None:
    sample_tree(tmp_path)
    registry = registry_for(tmp_path)
    data = json.loads(registry.get("tree").invoke({}))["data"]
    paths = {item["path"]: item["type"] for item in data["entries"]}
    assert paths == {
        "src": "directory",
        "src/deep": "directory",
        "src/main.py": "file",
        "src/deep/extra.py": "file",
        "src/note.md": "file",
        "top.py": "file",
    }
    assert "[D] src" in data["tree"]
    assert "[F] extra.py" in data["tree"]
    assert data["truncated"] is False
    shallow = json.loads(registry.get("tree").invoke({"max_depth": 1}))["data"]
    assert [item["path"] for item in shallow["entries"]] == ["src", "top.py"]
    assert all(item["depth"] == 1 for item in shallow["entries"])


def test_tree_depth_cannot_exceed_configured_limit(tmp_path: Path) -> None:
    sample_tree(tmp_path)
    data = json.loads(registry_for(tmp_path, max_depth=1).get("tree").invoke({"max_depth": 9}))[
        "data"
    ]
    assert data["max_depth"] == 1
    assert all(item["depth"] == 1 for item in data["entries"])


def test_tree_truncation_and_exact_limit(tmp_path: Path) -> None:
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).touch()
    data = json.loads(registry_for(tmp_path, max_entries=2).get("tree").invoke({}))["data"]
    assert len(data["entries"]) == 2
    assert data["truncated"] is True
    assert "truncated" in data["tree"]
    exact = json.loads(registry_for(tmp_path, max_entries=3).get("tree").invoke({}))["data"]
    assert exact["truncated"] is False


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("*.py", ["top.py"]),
        ("**/*.py", ["src/deep/extra.py", "src/main.py", "top.py"]),
        ("src/*.py", ["src/main.py"]),
        ("src/**/*.py", ["src/deep/extra.py", "src/main.py"]),
        ("**/m?in.[p]y", ["src/main.py"]),
        ("no-match*", []),
    ],
)
def test_glob_patterns_are_relative_to_workspace(
    tmp_path: Path, pattern: str, expected: list[str]
) -> None:
    sample_tree(tmp_path)
    data = json.loads(registry_for(tmp_path).get("glob_files").invoke({"pattern": pattern}))["data"]
    assert data["files"] == expected
    assert data["truncated"] is False


def test_glob_truncation_and_custom_exclusion(tmp_path: Path) -> None:
    sample_tree(tmp_path)
    limited = registry_for(
        tmp_path, max_entries=1, exclude_dirs=[".git", ".venv", "node_modules", "src"]
    )
    data = json.loads(limited.get("glob_files").invoke({"pattern": "**/*.py"}))["data"]
    assert data["files"] == ["top.py"]
    assert data["truncated"] is False
    limited = registry_for(tmp_path, max_entries=1)
    data = json.loads(limited.get("glob_files").invoke({"pattern": "**/*.py"}))["data"]
    assert len(data["files"]) == 1
    assert data["truncated"] is True


@pytest.mark.parametrize("pattern", ["../*", "/etc/*", "src/../../*", "bad\x00glob"])
def test_invalid_glob_does_not_escape(tmp_path: Path, pattern: str) -> None:
    result = json.loads(registry_for(tmp_path).get("glob_files").invoke({"pattern": pattern}))
    assert result["error"]["code"] == "INVALID_ARGUMENT"


def test_external_links_omitted_and_internal_directory_links_not_followed(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    (tmp_path / "secret.py").write_text("secret", encoding="utf-8")
    (workspace / "escape.py").symlink_to(tmp_path / "secret.py")
    (workspace / "back").symlink_to(workspace, target_is_directory=True)
    (workspace / "local.py").touch()
    registry = registry_for(workspace)
    tree = json.loads(registry.get("tree").invoke({}))["data"]
    assert [item["path"] for item in tree["entries"]] == ["back", "local.py"]
    assert tree["entries"][0]["type"] == "symlink"
    glob = json.loads(registry.get("glob_files").invoke({"pattern": "**/*.py"}))["data"]
    assert glob["files"] == ["local.py"]
    result = json.loads(registry.get("tree").invoke({"path": ".."}))
    assert result["error"]["code"] == "PATH_OUTSIDE_WORKSPACE"


def test_subdirectory_root_and_non_directory_error(tmp_path: Path) -> None:
    sample_tree(tmp_path)
    registry = registry_for(tmp_path)
    result = json.loads(registry.get("tree").invoke({"path": "src"}))["data"]
    assert result["path"] == "src"
    assert "top.py" not in result["tree"]
    assert (
        json.loads(registry.get("tree").invoke({"path": "top.py"}))["error"]["code"]
        == "NOT_DIRECTORY"
    )
