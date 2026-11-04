"""Guarded UTF-8 viewing and atomic create, replace and insert operations."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from minimum_coding_agent.tools.base import ToolArguments, ToolContext
from minimum_coding_agent.tools.errors import ToolError


class ViewArguments(ToolArguments):
    """Arguments for file ranges or direct directory listings."""

    path: str = Field(min_length=1, description="Workspace file or directory.")
    view_range: list[int] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Inclusive [start, end], 1-based; end=-1 reads to EOF. Files only.",
    )


class CreateArguments(ToolArguments):
    """Arguments for exclusive file creation."""

    path: str = Field(min_length=1, description="New workspace file; parent must exist.")
    file_text: str = Field(description="UTF-8 text to write without overwriting an existing path.")


class ReplaceArguments(ToolArguments):
    """Arguments for exactly one literal substring replacement."""

    path: str = Field(min_length=1, description="Existing UTF-8 workspace file.")
    old_str: str = Field(
        min_length=1, description="Nonempty literal text that must occur exactly once."
    )
    new_str: str = Field(description="Replacement text, including any desired newlines.")


class InsertArguments(ToolArguments):
    """Arguments for inserting lines after a 1-based line or at the beginning."""

    path: str = Field(min_length=1, description="Existing UTF-8 workspace file.")
    insert_line: int = Field(ge=0, description="Insert after this line; 0 prepends, EOF appends.")
    new_str: str = Field(description="Text to insert; missing separating newlines are added.")


def _text_bytes(ctx: ToolContext, text: str) -> bytes:
    """Validate UTF-8 text and its byte limit before touching a target."""
    if "\x00" in text:
        raise ToolError("BINARY_FILE", "NUL bytes are not supported", "Use a UTF-8 text file.")
    try:
        data = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ToolError("BINARY_FILE", "text is not valid UTF-8", "Use valid UTF-8 text.") from exc
    if len(data) > ctx.settings.tools.editor.max_file_size_kb * 1024:
        raise ToolError(
            "FILE_TOO_LARGE",
            "file exceeds the editor size limit",
            "Increase tools.editor.max_file_size_kb.",
        )
    return data


def _read_text(ctx: ToolContext, target: Path) -> str:
    """Read at most the configured byte limit and reject binary/special files."""
    if not target.is_file():
        raise ToolError(
            "NOT_FILE", "operation requires a regular file", "Use view or tree for directories."
        )
    limit = ctx.settings.tools.editor.max_file_size_kb * 1024
    with target.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ToolError(
            "FILE_TOO_LARGE",
            "file exceeds the editor size limit",
            "Increase tools.editor.max_file_size_kb.",
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError("BINARY_FILE", "file is not UTF-8 text", "Use a UTF-8 text file.") from exc
    if "\x00" in text:
        raise ToolError("BINARY_FILE", "binary files are not supported", "Use a UTF-8 text file.")
    return text


def _atomic_write(ctx: ToolContext, target: Path, data: bytes, *, create: bool = False) -> None:
    """Stage complete bytes beside the target, then atomically publish them."""
    ctx.guard.resolve(target, must_exist=not create)
    mode = None if create else stat.S_IMODE(target.stat().st_mode)
    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=".mca-edit-", delete=False
        ) as stream:
            staged = Path(stream.name)
            stream.write(data)
            if mode is not None:
                os.fchmod(stream.fileno(), mode)
            stream.flush()
            os.fsync(stream.fileno())
        ctx.guard.resolve(target, must_exist=not create)
        if create:
            # link() atomically publishes complete contents and refuses any existing entry.
            os.link(staged, target)
        else:
            os.replace(staged, target)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def _directory_view(ctx: ToolContext, target: Path) -> dict[str, Any]:
    """Return bounded direct children, omitting excluded dirs and unsafe symlinks."""
    settings = ctx.settings.tools.filesystem
    entries: list[dict[str, Any]] = []
    truncated = False
    for child in sorted(target.iterdir(), key=lambda item: item.name):
        try:
            resolved = ctx.guard.resolve(child)
        except ToolError:
            continue
        if child.name in settings.exclude_dirs and resolved.is_dir():
            continue
        if len(entries) >= settings.max_entries:
            truncated = True
            break
        kind = (
            "symlink"
            if child.is_symlink()
            else ("directory" if child.is_dir() else "file" if child.is_file() else "other")
        )
        entries.append({"name": child.name, "type": kind, "size_bytes": child.lstat().st_size})
    return {"type": "directory", "entries": entries, "truncated": truncated}


class EditorToolset:
    """Expose bounded viewing and all-or-nothing UTF-8 editing."""

    name = "editor"

    def build(self, ctx: ToolContext) -> list[BaseTool]:
        """Build the four editor tools using the shared path guard and limits.

        Args:
            ctx: Workspace and editor configuration.

        Returns:
            ``view``, ``create``, ``str_replace`` and ``insert`` tools.
        """

        @tool(args_schema=ViewArguments)
        def view(path: str, view_range: list[int] | None = None) -> dict[str, Any]:
            """View numbered UTF-8 lines or a directory's direct children and sizes.

            Args:
                path: Workspace file or directory.
                view_range: Inclusive 1-based line range; end=-1 reads to EOF. Files only.

            Returns:
                Bounded numbered text or a direct directory listing with metadata.

            Raises:
                ToolError: If a directory range is supplied or a file range is invalid.
            """
            target = ctx.guard.resolve(path)
            if target.is_dir():
                if view_range is not None:
                    raise ToolError(
                        "INVALID_ARGUMENT", "directories have no line ranges", "Omit view_range."
                    )
                return _directory_view(ctx, target)
            lines = _read_text(ctx, target).splitlines()
            start, end = (1, len(lines)) if view_range is None else view_range
            if end == -1:
                end = len(lines)
            if view_range is not None and (
                start < 1 or start > len(lines) or end < start or end > len(lines)
            ):
                raise ToolError(
                    "INVALID_RANGE",
                    "line range is outside the file",
                    "Use 1-based inclusive lines; end=-1 means EOF.",
                )
            content = "\n".join(
                f"{number}: {lines[number - 1]}" for number in range(start, end + 1)
            )
            limit = ctx.settings.tools.editor.max_output_chars
            truncated = len(content) > limit
            if truncated:
                marker = "\n[... truncated: output limit reached ...]"
                content = content[: limit - len(marker)] + marker
            return {
                "type": "file",
                "content": content,
                "start_line": start,
                "end_line": end,
                "total_lines": len(lines),
                "truncated": truncated,
            }

        @tool(args_schema=CreateArguments)
        def create(path: str, file_text: str) -> dict[str, Any]:
            """Create a complete UTF-8 file atomically without overwriting an existing path.

            Args:
                path: New file path whose parent directory already exists.
                file_text: UTF-8 text within the configured byte limit.

            Returns:
                Canonical workspace-relative path and byte count.

            Raises:
                ToolError: If the target already exists, including a dangling symlink.
            """
            target = ctx.guard.resolve(path, must_exist=False)
            supplied = Path(path)
            lexical = supplied if supplied.is_absolute() else ctx.guard.root / supplied
            if lexical.exists() or lexical.is_symlink():
                raise ToolError(
                    "ALREADY_EXISTS", "target already exists", "Choose a new path or edit it."
                )
            data = _text_bytes(ctx, file_text)
            _atomic_write(ctx, target, data, create=True)
            return {
                "path": target.relative_to(ctx.guard.root).as_posix(),
                "bytes_written": len(data),
            }

        @tool(args_schema=ReplaceArguments)
        def str_replace(path: str, old_str: str, new_str: str) -> dict[str, Any]:
            """Replace exactly one literal occurrence, leaving failed matches unchanged.

            Args:
                path: Existing UTF-8 workspace file.
                old_str: Nonempty substring that occurs exactly once, including overlaps.
                new_str: Replacement text, with newlines preserved verbatim.

            Returns:
                Canonical workspace-relative path and a replacement count of one.

            Raises:
                ToolError: If the old text is missing or occurs more than once.
            """
            target = ctx.guard.resolve(path)
            text = _read_text(ctx, target)
            first = text.find(old_str)
            if first < 0:
                raise ToolError(
                    "MATCH_NOT_FOUND", "old_str was not found", "Copy an exact substring from view."
                )
            if text.find(old_str, first + 1) >= 0:
                raise ToolError(
                    "MATCH_NOT_UNIQUE",
                    "old_str occurs more than once",
                    "Include more surrounding context.",
                )
            result = text[:first] + new_str + text[first + len(old_str) :]
            data = _text_bytes(ctx, result)
            _atomic_write(ctx, target, data)
            return {"path": target.relative_to(ctx.guard.root).as_posix(), "replacements": 1}

        @tool(args_schema=InsertArguments)
        def insert(path: str, insert_line: int, new_str: str) -> dict[str, Any]:
            """Insert after a 1-based line or prepend at line 0, adding separating newlines.

            Args:
                path: Existing UTF-8 workspace file.
                insert_line: Line after which to insert; 0 prepends and line count appends.
                new_str: Text to insert; an empty string is a no-op.

            Returns:
                Canonical workspace-relative path and the insertion position.

            Raises:
                ToolError: If the insertion position exceeds the file's line count.
            """
            target = ctx.guard.resolve(path)
            text = _read_text(ctx, target)
            lines = text.splitlines(keepends=True)
            if insert_line > len(lines):
                raise ToolError(
                    "INVALID_RANGE",
                    "insert_line is outside the file",
                    "Use 0 through the file's line count.",
                )
            if new_str:
                prefix, suffix = "".join(lines[:insert_line]), "".join(lines[insert_line:])
                newline = "\r\n" if "\r\n" in text else "\n"
                if prefix and not prefix.endswith(("\r", "\n")):
                    prefix += newline
                if suffix and not new_str.endswith(("\r", "\n")):
                    new_str += newline
                data = _text_bytes(ctx, prefix + new_str + suffix)
                _atomic_write(ctx, target, data)
            return {
                "path": target.relative_to(ctx.guard.root).as_posix(),
                "insert_line": insert_line,
            }

        return [view, create, str_replace, insert]
