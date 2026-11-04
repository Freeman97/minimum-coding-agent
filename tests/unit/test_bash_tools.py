"""Real subprocess tests for limits, environment isolation and group termination."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.tools.base import ConfirmCommand, ToolContext
from minimum_coding_agent.tools.bash import BashPolicy, BashToolset
from minimum_coding_agent.tools.registry import ToolRegistry


def python_command(source: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(source)}"


def command_tool(
    workspace: Path,
    *,
    confirm_command: ConfirmCommand | None = None,
    policy: BashPolicy | None = None,
    environ: dict[str, str] | None = None,
    **options: Any,
) -> Any:
    ctx = ToolContext(
        Settings(workspace=workspace, tools={"bash": options}),
        confirm_command=confirm_command,
        environ={} if environ is None else environ,
    )
    registry = ToolRegistry(ctx)
    registry.register(BashToolset(policy))
    return registry.get("run_command")


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    status = Path(f"/proc/{pid}/stat")
    if status.exists():
        return status.read_text().split(")", 1)[1].split()[0] != "Z"
    return True


@pytest.mark.asyncio
async def test_command_workspace_stdout_stderr_exit_code_and_closed_stdin(tmp_path: Path) -> None:
    script = (
        "import pathlib,sys; print(pathlib.Path.cwd()); print(sys.stdin.read()); "
        "print('diagnostic',file=sys.stderr)"
    )
    result = json.loads(await command_tool(tmp_path).ainvoke({"command": python_command(script)}))
    assert result["ok"] is True
    assert result["data"]["stdout"] == f"{tmp_path}\n\n"
    assert result["data"]["stderr"] == "diagnostic\n"
    assert result["data"]["exit_code"] == 0
    assert result["data"]["timed_out"] is False


@pytest.mark.asyncio
async def test_failed_command_returns_stderr_and_exit_code(tmp_path: Path) -> None:
    script = "import sys; print('out'); print('failure',file=sys.stderr); sys.exit(7)"
    result = json.loads(await command_tool(tmp_path).ainvoke({"command": python_command(script)}))
    assert result["ok"] is False
    assert result["error"]["code"] == "COMMAND_FAILED"
    assert result["data"]["exit_code"] == 7
    assert result["data"]["stdout"] == "out\n"
    assert result["data"]["stderr"] == "failure\n"


@pytest.mark.asyncio
async def test_head_tail_truncation_independent_for_both_streams(tmp_path: Path) -> None:
    source = (
        "import sys; "
        "sys.stdout.write('HEAD-OUT'+('中'*100000)+'TAIL-OUT'); "
        "sys.stderr.write('HEAD-ERR'+('x'*100000)+'TAIL-ERR')"
    )
    tool = command_tool(tmp_path, max_output_chars=1000)
    result = json.loads(await tool.ainvoke({"command": python_command(source)}))["data"]
    for stream, label in (("stdout", "OUT"), ("stderr", "ERR")):
        assert len(result[stream]) == 1000
        assert result[stream].startswith(f"HEAD-{label}")
        assert result[stream].endswith(f"TAIL-{label}")
        assert "truncated" in result[stream]
        assert "�" not in result[stream]
        assert result[f"{stream}_truncated"] is True


@pytest.mark.asyncio
async def test_exact_output_limit_is_not_truncated(tmp_path: Path) -> None:
    tool = command_tool(tmp_path, max_output_chars=1000)
    result = json.loads(await tool.ainvoke({"command": python_command("print('x'*1000,end='')")}))[
        "data"
    ]
    assert result["stdout"] == "x" * 1000
    assert result["stdout_truncated"] is False


@pytest.mark.asyncio
async def test_sleep_timeout_terminates_command_and_retains_partial_output(tmp_path: Path) -> None:
    tool = command_tool(tmp_path, timeout_seconds=0.15)
    started = time.monotonic()
    result = json.loads(await tool.ainvoke({"command": "printf 'started\\n'; sleep 30"}))
    assert time.monotonic() - started < 3
    assert result["error"]["code"] == "TIMEOUT"
    assert result["data"]["stdout"] == "started\n"
    assert result["data"]["timed_out"] is True


@pytest.mark.asyncio
async def test_timeout_kills_descendant_process_group(tmp_path: Path) -> None:
    source = (
        "import os,pathlib,time; "
        "pathlib.Path('child.pid').write_text(str(os.getpid())); time.sleep(30)"
    )
    tool = command_tool(tmp_path, timeout_seconds=0.4)
    result = json.loads(await tool.ainvoke({"command": python_command(source) + " & wait"}))
    assert result["error"]["code"] == "TIMEOUT"
    pid = int((tmp_path / "child.pid").read_text())
    for _ in range(50):
        if not process_running(pid):
            break
        await asyncio.sleep(0.01)
    assert not process_running(pid)


@pytest.mark.asyncio
async def test_cancellation_cleans_up_children(tmp_path: Path) -> None:
    source = (
        "import os,pathlib,time; "
        "pathlib.Path('child.pid').write_text(str(os.getpid())); time.sleep(30)"
    )
    tool = command_tool(tmp_path)
    task = asyncio.create_task(tool.ainvoke({"command": python_command(source) + " & wait"}))
    try:
        for _ in range(200):
            if (tmp_path / "child.pid").exists():
                break
            await asyncio.sleep(0.01)
        assert (tmp_path / "child.pid").exists()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    pid = int((tmp_path / "child.pid").read_text())
    for _ in range(50):
        if not process_running(pid):
            break
        await asyncio.sleep(0.01)
    assert not process_running(pid)


@pytest.mark.asyncio
async def test_timeout_while_continuously_filling_both_pipes(tmp_path: Path) -> None:
    source = "import os\nwhile True:\n os.write(1,b'x'*8192)\n os.write(2,b'y'*8192)"
    tool = command_tool(tmp_path, timeout_seconds=0.1, max_output_chars=1000)
    result = json.loads(
        await asyncio.wait_for(tool.ainvoke({"command": python_command(source)}), 3)
    )
    assert result["error"]["code"] == "TIMEOUT"
    assert result["data"]["stdout_truncated"] is True
    assert result["data"]["stderr_truncated"] is True


@pytest.mark.asyncio
async def test_shell_exit_does_not_leave_background_process_alive(tmp_path: Path) -> None:
    command = "sleep 30 >/dev/null 2>&1 & printf '%s' $! > child.pid"
    result = json.loads(await command_tool(tmp_path).ainvoke({"command": command}))
    assert result["ok"] is True
    pid = int((tmp_path / "child.pid").read_text())
    for _ in range(50):
        if not process_running(pid):
            break
        await asyncio.sleep(0.01)
    assert not process_running(pid)


@pytest.mark.asyncio
async def test_command_timeout_cannot_raise_configured_limit(tmp_path: Path) -> None:
    tool = command_tool(tmp_path, timeout_seconds=0.1)
    result = json.loads(await tool.ainvoke({"command": "sleep 30", "timeout_seconds": 10}))
    assert result["error"]["code"] == "TIMEOUT"
    assert "0.1 seconds" in result["error"]["message"]


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf x",
        "rm -fr x",
        "rm --recursive --force x",
        "/bin/rm -r x",
        "printf hello && rm -r -f x",
        "git reset --hard HEAD",
        "git -C repo reset --hard",
        "git clean -fd",
        "git clean -xfd",
        "git clean --force -d",
        "sudo echo x",
        "/sbin/mkfs.ext4 /dev/fake",
        "dd if=/dev/zero of=file",
        "bash -c 'rm -rf x'",
        "echo $(rm -rf x)",
        "echo `rm -rf x`",
        "eval 'rm -rf x'",
    ],
)
def test_dangerous_command_patterns(command: str) -> None:
    assert BashPolicy().should_confirm(command)


@pytest.mark.parametrize(
    "command", ["ls", "git status --short", "pytest", "printf 'rm -rf literal'", "echo hello"]
)
def test_normal_commands_do_not_require_confirmation(command: str) -> None:
    assert not BashPolicy().should_confirm(command)


@pytest.mark.asyncio
async def test_headless_dangerous_command_is_denied_before_execution(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep/file").write_bytes(b"safe")
    result = json.loads(await command_tool(tmp_path).ainvoke({"command": "rm -rf keep"}))
    assert result["error"]["code"] == "COMMAND_DENIED"
    assert (tmp_path / "keep/file").read_bytes() == b"safe"


class AlwaysConfirm(BashPolicy):
    def should_confirm(self, command: str) -> bool:
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [True, False])
async def test_confirmation_callback_controls_execution(tmp_path: Path, approved: bool) -> None:
    calls: list[str] = []

    async def confirm(command: str) -> bool:
        calls.append(command)
        return approved

    command = "printf approved > result.txt"
    tool = command_tool(tmp_path, policy=AlwaysConfirm(), confirm_command=confirm)
    result = json.loads(await tool.ainvoke({"command": command}))
    assert calls == [command]
    assert result["ok"] is approved
    assert (tmp_path / "result.txt").exists() is approved


@pytest.mark.asyncio
async def test_confirmation_switch_can_be_disabled_explicitly(tmp_path: Path) -> None:
    tool = command_tool(tmp_path, policy=AlwaysConfirm(), confirm_dangerous_commands=False)
    result = json.loads(await tool.ainvoke({"command": "printf allowed"}))
    assert result["ok"] is True
    assert result["data"]["stdout"] == "allowed"


@pytest.mark.asyncio
async def test_secret_environment_and_shell_startup_hooks_are_removed(tmp_path: Path) -> None:
    hook = tmp_path / "hook.sh"
    hook.write_text("printf unsafe > startup-ran\n", encoding="utf-8")
    environment = {
        "PATH": "/usr/bin:/bin",
        "WORK_TAG": "kept",
        "CUSTOM_AUTH": "provider-key",
        "MCA_API_KEY": "fake-mca",
        "MCA_LIVE_API_KEY": "fake-live",
        "OPENAI_API_KEY": "fake-openai",
        "DEEPSEEK_API_KEY": "fake-deepseek",
        "AWS_SESSION_TOKEN": "fake-aws",
        "SERVICE_PASSWORD": "fake-pass",
        "BASH_ENV": str(hook),
    }
    ctx = ToolContext(
        Settings(workspace=tmp_path, provider={"api_key_env": "CUSTOM_AUTH"}), environ=environment
    )
    registry = ToolRegistry(ctx)
    registry.register(BashToolset())
    result = json.loads(
        await registry.get("run_command").ainvoke(
            {"command": python_command("import json,os; print(json.dumps(dict(os.environ)))")}
        )
    )
    child_env = json.loads(result["data"]["stdout"])
    assert child_env["WORK_TAG"] == "kept"
    assert child_env["PATH"] == "/usr/bin:/bin"
    assert not ctx.secret_env_names().intersection(child_env)
    assert "BASH_ENV" not in child_env
    assert not (tmp_path / "startup-ran").exists()
    assert environment["CUSTOM_AUTH"] == "provider-key"


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
async def test_invalid_timeout_returns_structured_error(tmp_path: Path, timeout: float) -> None:
    result = json.loads(
        await command_tool(tmp_path).ainvoke({"command": "echo hi", "timeout_seconds": timeout})
    )
    assert result["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["", "   ", "bad\x00command"])
async def test_empty_or_invalid_command_is_rejected(tmp_path: Path, command: str) -> None:
    result = json.loads(await command_tool(tmp_path).ainvoke({"command": command}))
    assert result["error"]["code"] == "INVALID_ARGUMENT"
