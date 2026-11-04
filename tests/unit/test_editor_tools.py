"""Editor range conventions, exact edits and all-or-nothing filesystem effects."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.tools.base import ToolContext
from minimum_coding_agent.tools.editor import EditorToolset
from minimum_coding_agent.tools.registry import ToolRegistry


def registry_for(workspace: Path, **options: Any) -> ToolRegistry:
    settings = Settings(workspace=workspace, tools={"editor": options})
    registry = ToolRegistry(ToolContext(settings, environ={}))
    registry.register(EditorToolset())
    return registry


def invoke(registry: ToolRegistry, name: str, **args: Any) -> dict[str, Any]:
    return json.loads(registry.get(name).invoke(args))


def test_view_numbered_file_and_eof_range(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    registry = registry_for(tmp_path)
    result = invoke(registry, "view", path="sample.txt")["data"]
    assert result == {
        "type": "file",
        "content": "1: one\n2: two\n3: three",
        "start_line": 1,
        "end_line": 3,
        "total_lines": 3,
        "truncated": False,
    }
    data = invoke(registry, "view", path="sample.txt", view_range=[2, -1])["data"]
    assert data["content"] == "2: two\n3: three"
    assert (
        invoke(registry, "view", path="sample.txt", view_range=[2, 2])["data"]["content"]
        == "2: two"
    )


@pytest.mark.parametrize("view_range", [[0, -1], [2, 1], [4, -1], [1, 99], [-1, 1]])
def test_invalid_view_ranges_return_error(tmp_path: Path, view_range: list[int]) -> None:
    target = tmp_path / "text"
    target.write_bytes(b"one\ntwo\n")
    result = invoke(registry_for(tmp_path), "view", path="text", view_range=view_range)
    assert result["error"]["code"] == "INVALID_RANGE"
    assert target.read_bytes() == b"one\ntwo\n"


def test_empty_file_view(tmp_path: Path) -> None:
    (tmp_path / "empty").touch()
    data = invoke(registry_for(tmp_path), "view", path="empty")["data"]
    assert data["content"] == ""
    assert data["total_lines"] == 0


def test_directory_view_is_nonrecursive_with_type_and_size(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/nested.txt").touch()
    (tmp_path / "file.txt").write_bytes(b"123")
    (tmp_path / ".git").mkdir()
    registry = registry_for(tmp_path)
    data = invoke(registry, "view", path=".")["data"]
    assert [entry["name"] for entry in data["entries"]] == ["file.txt", "sub"]
    assert data["entries"][0] == {"name": "file.txt", "type": "file", "size_bytes": 3}
    assert data["entries"][1]["type"] == "directory"
    assert (
        invoke(registry, "view", path=".", view_range=[1, -1])["error"]["code"]
        == "INVALID_ARGUMENT"
    )


def test_view_output_limit_marks_truncation(tmp_path: Path) -> None:
    (tmp_path / "long.txt").write_text("x" * 4000, encoding="utf-8")
    result = invoke(registry_for(tmp_path, max_output_chars=1000), "view", path="long.txt")["data"]
    assert result["truncated"] is True
    assert len(result["content"]) == 1000
    assert "truncated" in result["content"]


@pytest.mark.parametrize("data", [b"binary\x00data", b"\xff\xfe\xfd"])
@pytest.mark.parametrize("name", ["view", "str_replace", "insert"])
def test_binary_files_rejected_without_modification(tmp_path: Path, data: bytes, name: str) -> None:
    target = tmp_path / "binary"
    target.write_bytes(data)
    args: dict[str, Any] = {"path": "binary"}
    if name == "str_replace":
        args.update(old_str="binary", new_str="text")
    if name == "insert":
        args.update(insert_line=0, new_str="text")
    assert invoke(registry_for(tmp_path), name, **args)["error"]["code"] == "BINARY_FILE"
    assert target.read_bytes() == data


def test_size_limit_applies_before_reads_and_writes(tmp_path: Path) -> None:
    registry = registry_for(tmp_path, max_file_size_kb=1)
    target = tmp_path / "large.txt"
    target.write_bytes(b"x" * 1025)
    assert invoke(registry, "view", path="large.txt")["error"]["code"] == "FILE_TOO_LARGE"
    assert (
        invoke(registry, "create", path="new.txt", file_text="中" * 400)["error"]["code"]
        == "FILE_TOO_LARGE"
    )
    assert not (tmp_path / "new.txt").exists()
    target.write_bytes(b"small")
    result = invoke(registry, "str_replace", path="large.txt", old_str="small", new_str="x" * 1025)
    assert result["error"]["code"] == "FILE_TOO_LARGE"
    assert target.read_bytes() == b"small"


def test_create_never_clobbers_existing_files_or_links(tmp_path: Path) -> None:
    registry = registry_for(tmp_path)
    result = invoke(registry, "create", path="new.txt", file_text="hello\n")
    assert result == {"ok": True, "data": {"path": "new.txt", "bytes_written": 6}}
    assert (tmp_path / "new.txt").read_bytes() == b"hello\n"
    assert (
        invoke(registry, "create", path="new.txt", file_text="replace")["error"]["code"]
        == "ALREADY_EXISTS"
    )
    assert (tmp_path / "new.txt").read_bytes() == b"hello\n"
    (tmp_path / "dangling").symlink_to("missing")
    assert (
        invoke(registry, "create", path="dangling", file_text="replace")["error"]["code"]
        == "ALREADY_EXISTS"
    )
    assert not (tmp_path / "missing").exists()
    assert (
        invoke(registry, "create", path="absent/new.txt", file_text="text")["error"]["code"]
        == "NOT_FOUND"
    )
    assert not (tmp_path / "absent").exists()


def test_unique_replace_preserves_crlf_and_permissions(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_bytes(b"one\r\ntwo\r\nthree\r\n")
    target.chmod(0o754)
    result = invoke(
        registry_for(tmp_path), "str_replace", path="sample.txt", old_str="two", new_str="second"
    )
    assert result["data"]["replacements"] == 1
    assert target.read_bytes() == b"one\r\nsecond\r\nthree\r\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o754


@pytest.mark.parametrize(
    ("text", "old", "code"),
    [
        ("one\none\n", "one", "MATCH_NOT_UNIQUE"),
        ("aaa", "aa", "MATCH_NOT_UNIQUE"),
        ("one", "absent", "MATCH_NOT_FOUND"),
    ],
)
def test_failed_replace_does_not_modify_file(
    tmp_path: Path, text: str, old: str, code: str
) -> None:
    target = tmp_path / "sample.txt"
    target.write_text(text, encoding="utf-8")
    original = target.read_bytes()
    result = invoke(
        registry_for(tmp_path), "str_replace", path="sample.txt", old_str=old, new_str="new"
    )
    assert result["error"]["code"] == code
    assert target.read_bytes() == original


@pytest.mark.parametrize(
    ("text", "line", "added", "expected"),
    [
        ("one\ntwo\n", 0, "zero", "zero\none\ntwo\n"),
        ("one\ntwo\n", 1, "middle", "one\nmiddle\ntwo\n"),
        ("one\ntwo\n", 2, "last", "one\ntwo\nlast"),
        ("one\ntwo", 2, "last", "one\ntwo\nlast"),
        ("one\r\ntwo\r\n", 1, "middle", "one\r\nmiddle\r\ntwo\r\n"),
        ("", 0, "first", "first"),
        ("one", 1, "", "one"),
    ],
)
def test_insert_boundaries_and_line_endings(
    tmp_path: Path, text: str, line: int, added: str, expected: str
) -> None:
    target = tmp_path / "sample.txt"
    target.write_bytes(text.encode("utf-8"))
    result = invoke(
        registry_for(tmp_path), "insert", path="sample.txt", insert_line=line, new_str=added
    )
    assert result["ok"] is True
    assert target.read_bytes() == expected.encode("utf-8")


@pytest.mark.parametrize("line", [-1, 3])
def test_out_of_bounds_insert_leaves_file_unchanged(tmp_path: Path, line: int) -> None:
    target = tmp_path / "sample.txt"
    target.write_bytes(b"one\ntwo\n")
    result = invoke(
        registry_for(tmp_path), "insert", path="sample.txt", insert_line=line, new_str="bad"
    )
    assert result["ok"] is False
    assert target.read_bytes() == b"one\ntwo\n"


@pytest.mark.parametrize("name", ["view", "create", "str_replace", "insert"])
def test_editor_rejects_external_symlink_paths(tmp_path: Path, name: str) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    private = tmp_path / "private.txt"
    private.write_bytes(b"private")
    (workspace / "link").symlink_to(tmp_path, target_is_directory=True)
    args: dict[str, Any] = {"path": "link/private.txt"}
    if name == "create":
        args.update(path="link/new.txt", file_text="new")
    elif name == "str_replace":
        args.update(old_str="private", new_str="public")
    elif name == "insert":
        args.update(insert_line=0, new_str="new")
    assert (
        invoke(registry_for(workspace), name, **args)["error"]["code"] == "PATH_OUTSIDE_WORKSPACE"
    )
    assert private.read_bytes() == b"private"
    assert not (tmp_path / "new.txt").exists()


def test_failed_atomic_replace_leaves_original_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "sample.txt"
    target.write_bytes(b"original")

    def fail_replace(source: object, destination: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(os, "replace", fail_replace)
    result = invoke(
        registry_for(tmp_path), "str_replace", path="sample.txt", old_str="original", new_str="new"
    )
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert target.read_bytes() == b"original"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["sample.txt"]


def test_atomic_create_handles_a_competing_creator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_link = os.link

    def competing_link(source: Path, destination: Path) -> None:
        destination.write_bytes(b"competitor")
        original_link(source, destination)

    monkeypatch.setattr(os, "link", competing_link)
    result = invoke(registry_for(tmp_path), "create", path="new.txt", file_text="ours")
    assert result["error"]["code"] == "ALREADY_EXISTS"
    assert (tmp_path / "new.txt").read_bytes() == b"competitor"
    assert not list(tmp_path.glob(".mca-edit-*"))
