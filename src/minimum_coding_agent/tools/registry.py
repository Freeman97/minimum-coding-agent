"""Assemble enabled toolsets and reject ambiguous model-visible names."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from minimum_coding_agent.tools.base import ToolContext, Toolset, protect_tool
from minimum_coding_agent.tools.errors import ToolRegistrationError


class ToolRegistry:
    """Collect tools transactionally, applying one shared result boundary."""

    def __init__(self, ctx: ToolContext) -> None:
        """Initialize an empty registry for a workspace.

        Args:
            ctx: Shared configuration and workspace context.
        """
        self.ctx = ctx
        self._tools: dict[str, BaseTool] = {}
        self._toolsets: set[str] = set()

    def register(self, toolset: Toolset, *, enabled: bool = True) -> None:
        """Build and register an enabled toolset, rejecting all name conflicts.

        Args:
            toolset: Toolset with a nonempty name and a callable ``build`` method.
            enabled: Whether to expose this toolset; disabled sets are not built.

        Raises:
            ToolRegistrationError: If the contract or a tool name is invalid.
        """
        if not enabled:
            return
        name = getattr(toolset, "name", None)
        if (
            not isinstance(name, str)
            or not name.strip()
            or not callable(getattr(toolset, "build", None))
        ):
            raise ToolRegistrationError("toolset requires a nonempty name and build(ctx)")
        if name in self._toolsets:
            raise ToolRegistrationError(f"toolset {name!r} is already registered")
        pending: dict[str, BaseTool] = {}
        for tool in toolset.build(self.ctx):
            if not isinstance(tool, BaseTool) or not tool.name.strip() or not tool.description:
                raise ToolRegistrationError(f"toolset {name!r} returned an invalid tool")
            if tool.name in self._tools or tool.name in pending:
                raise ToolRegistrationError(f"tool name {tool.name!r} is already registered")
            pending[tool.name] = protect_tool(tool, self.ctx)
        self._tools.update(pending)
        self._toolsets.add(name)

    def names(self) -> tuple[str, ...]:
        """List registered model-visible names.

        Returns:
            Tool names in alphabetical order.
        """
        return tuple(sorted(self._tools))

    def tools(self) -> list[BaseTool]:
        """Return the tool list for ``model.bind_tools`` or a LangGraph ToolNode.

        Returns:
            Registered tools in alphabetical name order.
        """
        return [self._tools[name] for name in self.names()]

    def get(self, name: str) -> BaseTool:
        """Look up a registered tool.

        Args:
            name: Exact model-visible tool name.

        Returns:
            Tool with a JSON result boundary.

        Raises:
            KeyError: If the name is not registered.
        """
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]
