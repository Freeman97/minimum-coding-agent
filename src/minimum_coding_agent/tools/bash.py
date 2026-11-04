"""Non-interactive Bash execution with bounded streams and process-group cleanup."""

from __future__ import annotations

import asyncio
import codecs
import os
import shlex
import signal
from pathlib import PurePosixPath
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from minimum_coding_agent.tools.base import ToolArguments, ToolContext
from minimum_coding_agent.tools.errors import ToolError


class CommandArguments(ToolArguments):
    """Arguments for a non-interactive command in the workspace root."""

    command: str = Field(min_length=1, description="Bash command; stdin is closed.")
    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Optional timeout in seconds, capped by tools.bash.timeout_seconds.",
    )


class BashPolicy:
    """Recognize common destructive commands; this is a heuristic, not a sandbox."""

    def should_confirm(self, command: str) -> bool:
        """Check commands and common option forms before a subprocess starts.

        Args:
            command: Raw command text supplied to Bash.

        Returns:
            Whether execution requires an explicit approval callback.
        """
        if "$(" in command or "`" in command:
            return True
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            return True
        for index, token in enumerate(tokens):
            name = PurePosixPath(token).name
            following: list[str] = []
            for item in tokens[index + 1 :]:
                if item in {";", "&&", "||", "|", "&", "(", ")"}:
                    break
                following.append(item)
            if (
                name in {"sudo", "dd", "eval", "source"}
                or name == "mkfs"
                or name.startswith("mkfs.")
            ):
                return True
            if name == "rm" and any(
                item == "--recursive"
                or (
                    item.startswith("-")
                    and not item.startswith("--")
                    and ("r" in item or "R" in item)
                )
                for item in following
            ):
                return True
            if name == "git":
                if "reset" in following and any(item.startswith("--hard") for item in following):
                    return True
                if "clean" in following and any(
                    item == "--force" or (item.startswith("-") and "f" in item)
                    for item in following
                ):
                    return True
            if name in {"bash", "sh", "zsh", "dash"} and "-c" in following:
                offset = following.index("-c") + 1
                if offset < len(following) and self.should_confirm(following[offset]):
                    return True
        return False


class _OutputBuffer:
    """Drain arbitrarily large output while keeping only bounded head/tail text."""

    def __init__(self, limit: int) -> None:
        """Initialize bounded head and tail storage.

        Args:
            limit: Maximum rendered characters, including the truncation marker.
        """
        self.limit = limit
        self.head = ""
        self.tail = ""
        self.total = 0

    def append(self, text: str) -> None:
        """Retain at most two output limits regardless of stream size.

        Args:
            text: Next decoded stream fragment.
        """
        self.total += len(text)
        if len(self.head) < self.limit:
            self.head += text[: self.limit - len(self.head)]
        self.tail = (self.tail + text)[-self.limit :]

    def render(self) -> str:
        """Return intact output, or bounded head/tail output with a marker.

        Returns:
            Original output or truncated text of at most ``limit`` characters.
        """
        if self.total <= self.limit:
            return self.head
        marker = "\n[... truncated ...]\n"
        remaining = self.limit - len(marker)
        head_length = (remaining + 1) // 2
        tail_length = remaining // 2
        return self.head[:head_length] + marker + self.tail[-tail_length:]


async def _drain(stream: asyncio.StreamReader, buffer: _OutputBuffer) -> None:
    """Decode split UTF-8 chunks incrementally while continuously draining pipes."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    while chunk := await stream.read(8192):
        buffer.append(decoder.decode(chunk))
    buffer.append(decoder.decode(b"", final=True))


async def _kill_group(process: asyncio.subprocess.Process) -> None:
    """Kill the session's process group even when its shell has already exited."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await process.wait()


async def _execute(ctx: ToolContext, command: str, timeout: float) -> dict[str, Any]:
    """Execute with concurrent bounded readers and cancellation-safe child cleanup."""
    secret_names = ctx.secret_env_names()
    environment = {key: value for key, value in ctx.environ.items() if key not in secret_names}
    for key in ("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS"):
        environment.pop(key, None)
    process = await asyncio.create_subprocess_shell(
        command,
        executable="/bin/bash",
        cwd=ctx.guard.root,
        env=environment,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    stdout = _OutputBuffer(ctx.settings.tools.bash.max_output_chars)
    stderr = _OutputBuffer(ctx.settings.tools.bash.max_output_chars)
    assert process.stdout is not None and process.stderr is not None
    readers = [
        asyncio.create_task(_drain(process.stdout, stdout)),
        asyncio.create_task(_drain(process.stderr, stderr)),
    ]

    async def wait_complete() -> None:
        await process.wait()
        await asyncio.gather(*readers)

    waiter = asyncio.create_task(wait_complete())
    timed_out = False
    try:
        # Keep draining pipes during timeout cleanup so a full pipe cannot block wait().
        await asyncio.wait_for(asyncio.shield(waiter), timeout)
    except asyncio.TimeoutError:
        timed_out = True
    finally:
        # Normal completion also reaps background descendants instead of leaving them alive.
        await _kill_group(process)
        await asyncio.gather(*readers)
        await waiter
    data = {
        "exit_code": process.returncode,
        "stdout": stdout.render(),
        "stderr": stderr.render(),
        "stdout_truncated": stdout.total > stdout.limit,
        "stderr_truncated": stderr.total > stderr.limit,
        "timed_out": timed_out,
    }
    if timed_out:
        raise ToolError(
            "TIMEOUT",
            f"command exceeded {timeout:g} seconds",
            "Use a shorter command or adjust the configured timeout.",
            data=data,
        )
    if process.returncode != 0:
        raise ToolError(
            "COMMAND_FAILED",
            f"command exited with code {process.returncode}",
            "Inspect stdout and stderr before retrying.",
            data=data,
        )
    return data


class BashToolset:
    """Expose non-interactive commands with configurable confirmation policy."""

    name = "bash"

    def __init__(self, policy: BashPolicy | None = None) -> None:
        """Choose the command confirmation classifier.

        Args:
            policy: Optional custom policy; defaults to common destructive patterns.
        """
        self.policy = BashPolicy() if policy is None else policy

    def build(self, ctx: ToolContext) -> list[BaseTool]:
        """Build ``run_command`` without creating subprocesses at assembly time.

        Args:
            ctx: Workspace, shell limits, environment and confirmation callback.

        Returns:
            An async-only LangChain command tool.
        """

        @tool(args_schema=CommandArguments)
        async def run_command(command: str, timeout_seconds: float | None = None) -> dict[str, Any]:
            """Run non-interactive Bash with bounded stdout/stderr in the workspace.

            Args:
                command: Command text; stdin is closed and credential variables are removed.
                timeout_seconds: Optional timeout, capped by the configured maximum.

            Returns:
                Exit code, bounded stdout/stderr and timeout/truncation flags.

            Raises:
                ToolError: If arguments are invalid or command approval is denied.
            """
            if not command.strip() or "\x00" in command:
                raise ToolError(
                    "INVALID_ARGUMENT",
                    "command is empty or contains NUL",
                    "Supply a valid Bash command.",
                )
            settings = ctx.settings.tools.bash
            if settings.confirm_dangerous_commands and self.policy.should_confirm(command):
                if ctx.confirm_command is None or not await ctx.confirm_command(command):
                    raise ToolError(
                        "COMMAND_DENIED",
                        "dangerous command was not approved",
                        "Use a safer command or an explicit approval callback.",
                    )
            timeout = min(timeout_seconds or settings.timeout_seconds, settings.timeout_seconds)
            return await _execute(ctx, command, timeout)

        return [run_command]
