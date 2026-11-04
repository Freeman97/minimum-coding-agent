"""Configuration-driven assembly of the toolsets delivered in M2."""

from __future__ import annotations

from collections.abc import Mapping

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.tools.base import ConfirmCommand, ToolContext
from minimum_coding_agent.tools.bash import BashToolset
from minimum_coding_agent.tools.editor import EditorToolset
from minimum_coding_agent.tools.filesystem import FilesystemToolset
from minimum_coding_agent.tools.registry import ToolRegistry


def create_tool_registry(
    settings: Settings,
    *,
    confirm_command: ConfirmCommand | None = None,
    environ: Mapping[str, str] | None = None,
) -> ToolRegistry:
    """Assemble enabled filesystem, editor and Bash tools for one workspace.

    Args:
        settings: Application configuration with workspace and toolset limits.
        confirm_command: Async callback for dangerous commands; defaults to deny.
        environ: Explicit subprocess environment; defaults to a snapshot of ``os.environ``.

    Returns:
        Registered tools ready for model binding or direct invocation.
    """
    if environ is None:
        ctx = ToolContext(settings, confirm_command=confirm_command)
    else:
        ctx = ToolContext(settings, confirm_command=confirm_command, environ=environ)
    registry = ToolRegistry(ctx)
    registry.register(FilesystemToolset(), enabled=settings.tools.filesystem.enabled)
    registry.register(EditorToolset(), enabled=settings.tools.editor.enabled)
    registry.register(BashToolset(), enabled=settings.tools.bash.enabled)
    return registry
