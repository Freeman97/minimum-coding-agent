"""Resolve filesystem tool paths within one canonical workspace root."""

from __future__ import annotations

from pathlib import Path

from minimum_coding_agent.tools.errors import ToolError


class WorkspaceGuard:
    """Guard reads and writes against absolute, parent and symlink escapes."""

    def __init__(self, root: str | Path) -> None:
        """Pin the canonical workspace root.

        Args:
            root: An existing workspace directory.

        Raises:
            ToolError: If the workspace does not exist or is not a directory.
        """
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ToolError("INVALID_WORKSPACE", "workspace is not a directory", "Check workspace.")

    def resolve(self, path: str | Path, must_exist: bool = True) -> Path:
        """Resolve a path, then check containment before accessing its contents.

        Args:
            path: Absolute or workspace-relative target path.
            must_exist: Whether the resolved target must already exist.

        Returns:
            A canonical absolute path inside the workspace.

        Raises:
            ToolError: If the path is invalid, escapes the root or is missing.
        """
        try:
            candidate = Path(path)
            if not candidate.is_absolute():
                candidate = self.root / candidate
            resolved = candidate.resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            raise ToolError(
                "INVALID_PATH", "cannot resolve the requested path", "Check the path and symlinks."
            ) from exc
        if not resolved.is_relative_to(self.root):
            raise ToolError(
                "PATH_OUTSIDE_WORKSPACE",
                "path resolves outside the workspace",
                "Use a path inside the workspace; external symlinks are not allowed.",
            )
        if must_exist and not resolved.exists():
            raise ToolError(
                "NOT_FOUND", "path does not exist", "Check the workspace-relative path."
            )
        return resolved
