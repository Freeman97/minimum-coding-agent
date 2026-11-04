"""Command line interface for the minimum coding agent.

M0 provides the argument surface and the startup checks; M1 adds the provider
registry startup check. The interactive console and the headless runtime are
placeholders until their own modules land.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from enum import IntEnum
from pathlib import Path

from minimum_coding_agent import __version__
from minimum_coding_agent.config.loader import ConfigLoadError, load_settings
from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.config.validation import StartupValidationError, validate_startup
from minimum_coding_agent.llm.defaults import create_default_registry
from minimum_coding_agent.llm.errors import UnknownProviderError

PROG = "mca"


class ExitCode(IntEnum):
    """Process exit codes used by the ``mca`` entry point."""

    OK = 0
    USAGE_ERROR = 2
    CONFIG_ERROR = 3
    STARTUP_ERROR = 4


def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser.

    Returns:
        The parser for the ``mca`` command and its subcommands.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="path to a YAML configuration file",
    )
    common.add_argument(
        "--workspace",
        metavar="DIR",
        default=argparse.SUPPRESS,
        help="workspace directory used by the agent",
    )

    parser = argparse.ArgumentParser(
        prog=PROG,
        description="A minimal ReAct-style coding agent built for learning purposes.",
        parents=[common],
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROG} {__version__}",
        help="show the project version and exit",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    run_parser = subparsers.add_parser(
        "run",
        parents=[common],
        help="execute a single task without the interactive console",
        description="Execute a single task in headless mode (placeholder until M3).",
    )
    run_parser.add_argument("task", metavar="TASK", help="task description for the agent")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface.

    ``argparse`` raises :class:`SystemExit` for ``--help``, ``--version`` and
    usage errors; the returned exit code covers configuration, startup and
    placeholder success paths.

    Args:
        argv: Argument list used instead of ``sys.argv[1:]``; mainly for tests.

    Returns:
        The process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = getattr(args, "config", None)
    workspace = getattr(args, "workspace", None)
    try:
        settings = load_settings(
            Path(config_path) if config_path is not None else None,
            workspace=Path(workspace) if workspace is not None else None,
        )
    except ConfigLoadError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return int(ExitCode.CONFIG_ERROR)

    try:
        warnings = validate_startup(settings)
    except StartupValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.STARTUP_ERROR)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    # Until the composition root (app.py, M3) exists, the CLI resolves the
    # configured provider name so an unknown provider fails before any
    # interface starts and lists the registered alternatives.
    try:
        create_default_registry().get(settings.provider.name)
    except UnknownProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.STARTUP_ERROR)

    if args.command == "run":
        return _run_headless(settings, args.task)
    return _run_interactive(settings)


def _run_interactive(settings: Settings) -> int:
    """Report that the interactive console is not implemented yet.

    Args:
        settings: Validated application settings.

    Returns:
        The ``OK`` exit code.
    """
    print("Interactive console is not available yet (planned for M5).")
    print(f"Workspace: {settings.workspace}")
    print(f"Provider: {settings.provider.name}, model: {settings.provider.model}")
    print("Configuration and startup checks succeeded.")
    return int(ExitCode.OK)


def _run_headless(settings: Settings, task: str) -> int:
    """Report that the headless runtime is not implemented yet.

    Args:
        settings: Validated application settings.
        task: Task description received on the command line.

    Returns:
        The ``OK`` exit code.
    """
    print("Headless run is not available yet (planned for M3).")
    print(f"Task: {task}")
    print(f"Workspace: {settings.workspace}")
    print("Configuration and startup checks succeeded.")
    return int(ExitCode.OK)
