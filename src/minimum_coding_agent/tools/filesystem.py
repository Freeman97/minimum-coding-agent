"""Bounded workspace directory trees and glob matching without symlink traversal."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from minimum_coding_agent.tools.base import ToolArguments, ToolContext
from minimum_coding_agent.tools.errors import ToolError


class TreeArguments(ToolArguments):
    """Arguments for bounded recursive directory expansion."""

    path: str = Field(default=".", min_length=1, description="Workspace directory to expand.")
    max_depth: int | None = Field(
        default=None, ge=1, le=32, description="Depth, capped by tools.filesystem.max_depth."
    )


class GlobArguments(ToolArguments):
    """Arguments for workspace-relative file glob matching."""

    pattern: str = Field(
        min_length=1, description="Relative glob; ** matches zero or more directories."
    )


def _walk(
    ctx: ToolContext, directory: Path, max_depth: int | None = None
) -> Iterator[tuple[Path, int]]:
    """Walk sorted, guarded entries without recursing through symbolic links."""
    excluded = set(ctx.settings.tools.filesystem.exclude_dirs)

    def visit(parent: Path, depth: int) -> Iterator[tuple[Path, int]]:
        for entry in sorted(parent.iterdir(), key=lambda item: item.name):
            try:
                resolved = ctx.guard.resolve(entry)
            except ToolError:
                continue
            if entry.name in excluded and resolved.is_dir():
                continue
            yield entry, depth
            if (
                not entry.is_symlink()
                and resolved.is_dir()
                and (max_depth is None or depth < max_depth)
            ):
                yield from visit(resolved, depth + 1)

    yield from visit(directory, 1)


def _entry_type(entry: Path) -> str:
    """Describe an entry without opening file contents."""
    if entry.is_symlink():
        return "symlink"
    if entry.is_dir():
        return "directory"
    return "file" if entry.is_file() else "other"


def _matches(parts: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    """Match glob components with ** supporting zero or more path components."""
    if not pattern:
        return not parts
    if pattern[0] == "**":
        return _matches(parts, pattern[1:]) or bool(parts and _matches(parts[1:], pattern))
    return bool(
        parts and fnmatch.fnmatchcase(parts[0], pattern[0]) and _matches(parts[1:], pattern[1:])
    )


class FilesystemToolset:
    """Expose directory expansion and file matching within the workspace."""

    name = "filesystem"

    def build(self, ctx: ToolContext) -> list[BaseTool]:
        """Build ``tree`` and ``glob_files`` with configured exclusions and caps.

        Args:
            ctx: Workspace and filesystem limits.

        Returns:
            Two tools returning bounded directory and file metadata.
        """
        settings = ctx.settings.tools.filesystem

        @tool(args_schema=TreeArguments)
        def tree(path: str = ".", max_depth: int | None = None) -> dict[str, Any]:
            """Show a bounded recursive directory tree, skipping excluded and external links.

            Args:
                path: Workspace directory to expand.
                max_depth: Optional depth, capped by the configured maximum.

            Returns:
                Typed entries, a readable tree, effective depth and a truncation flag.

            Raises:
                ToolError: If the requested root is not a directory.
            """
            root = ctx.guard.resolve(path)
            if not root.is_dir():
                raise ToolError("NOT_DIRECTORY", "tree requires a directory", "Use view for files.")
            depth = min(max_depth or settings.max_depth, settings.max_depth)
            entries: list[dict[str, Any]] = []
            rendered: list[str] = [f"[D] {root.relative_to(ctx.guard.root).as_posix()}/"]
            truncated = False
            for entry, level in _walk(ctx, root, depth):
                if len(entries) >= settings.max_entries:
                    truncated = True
                    break
                kind = _entry_type(entry)
                entries.append(
                    {
                        "path": entry.relative_to(ctx.guard.root).as_posix(),
                        "type": kind,
                        "depth": level,
                    }
                )
                marker = {"directory": "D", "file": "F", "symlink": "L", "other": "?"}[kind]
                rendered.append(f"{'  ' * level}[{marker}] {entry.name}")
            if truncated:
                rendered.append("[... truncated: entry limit reached ...]")
            return {
                "path": root.relative_to(ctx.guard.root).as_posix(),
                "entries": entries,
                "tree": "\n".join(rendered),
                "max_depth": depth,
                "truncated": truncated,
            }

        @tool(args_schema=GlobArguments)
        def glob_files(pattern: str) -> dict[str, Any]:
            """Find files by root-relative glob, skipping excluded dirs and external links.

            Args:
                pattern: Relative glob supporting *, ?, character classes and recursive **.

            Returns:
                Matching file paths, the result limit and an explicit truncation flag.

            Raises:
                ToolError: If the glob is absolute or contains parent or NUL components.
            """
            glob = Path(pattern)
            if glob.is_absolute() or ".." in glob.parts or "\x00" in pattern:
                raise ToolError(
                    "INVALID_ARGUMENT",
                    "glob must be workspace-relative",
                    "Use a glob such as **/*.py.",
                )
            files: list[str] = []
            truncated = False
            for entry, _ in _walk(ctx, ctx.guard.root):
                relative = entry.relative_to(ctx.guard.root)
                if entry.is_file() and _matches(relative.parts, glob.parts):
                    if len(files) >= settings.max_entries:
                        truncated = True
                        break
                    files.append(relative.as_posix())
            return {"files": files, "truncated": truncated, "limit": settings.max_entries}

        return [tree, glob_files]
