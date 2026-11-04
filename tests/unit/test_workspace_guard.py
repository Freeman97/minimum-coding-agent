"""Canonical workspace boundaries, including symlink and missing-path escapes."""

from __future__ import annotations

from pathlib import Path

import pytest

from minimum_coding_agent.tools.errors import ToolError
from minimum_coding_agent.tools.workspace import WorkspaceGuard


def test_in_workspace_relative_absolute_and_new_paths(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path)
    existing = tmp_path / "sample.txt"
    existing.write_text("sample", encoding="utf-8")
    assert guard.resolve("sample.txt") == existing
    assert guard.resolve(existing) == existing
    assert guard.resolve("sub/new.txt", must_exist=False) == tmp_path / "sub/new.txt"
    assert guard.resolve(".") == tmp_path


@pytest.mark.parametrize("path", ["../outside.txt", "../../new/file.txt", "/etc/passwd"])
def test_escapes_are_rejected(tmp_path: Path, path: str) -> None:
    with pytest.raises(ToolError) as caught:
        WorkspaceGuard(tmp_path).resolve(path, must_exist=False)
    assert caught.value.code == "PATH_OUTSIDE_WORKSPACE"


def test_prefix_sibling_is_not_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    with pytest.raises(ToolError, match="outside"):
        WorkspaceGuard(workspace).resolve(tmp_path / "work-evil/new.txt", must_exist=False)


def test_symlink_escape_including_nonexistent_write_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("private", encoding="utf-8")
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    guard = WorkspaceGuard(workspace)
    for path in ("link/private.txt", "link/new.txt", "link/nested/new.txt"):
        with pytest.raises(ToolError, match="outside"):
            guard.resolve(path, must_exist=False)
    assert not (outside / "new.txt").exists()
    assert not (outside / "nested").exists()


def test_internal_symlink_is_supported(tmp_path: Path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("real", encoding="utf-8")
    (tmp_path / "alias").symlink_to(target)
    assert WorkspaceGuard(tmp_path).resolve("alias") == target


def test_missing_invalid_and_looping_paths(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path)
    with pytest.raises(ToolError) as missing:
        guard.resolve("missing")
    assert missing.value.code == "NOT_FOUND"
    with pytest.raises(ToolError) as invalid:
        guard.resolve("bad\x00path", must_exist=False)
    assert invalid.value.code == "INVALID_PATH"
    (tmp_path / "loop").symlink_to("loop")
    with pytest.raises(ToolError):
        guard.resolve("loop")


def test_workspace_must_be_an_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="directory"):
        WorkspaceGuard(tmp_path / "missing")
