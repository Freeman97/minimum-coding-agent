"""Run the M2 tools in a temporary workspace, without models or network access."""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.tools.defaults import create_tool_registry


async def main() -> int:
    """Exercise all seven delivered tools and assert file and process results."""
    with TemporaryDirectory(prefix="mca-tools-") as directory:
        workspace = Path(directory)
        registry = create_tool_registry(Settings(workspace=workspace), environ={})
        print(f"registered tools: {', '.join(registry.names())}")

        async def call(name: str, **arguments: Any) -> dict[str, Any]:
            result = json.loads(await registry.get(name).ainvoke(arguments))
            print(f"{name}: {json.dumps(result, ensure_ascii=False)}")
            return result

        assert (await call("create", path="hello.txt", file_text="first\nsecond\n"))["ok"]
        assert (await call("tree"))["data"]["entries"][0]["path"] == "hello.txt"
        assert (await call("glob_files", pattern="**/*.txt"))["data"]["files"] == ["hello.txt"]
        assert (await call("view", path="hello.txt", view_range=[2, -1]))["data"][
            "content"
        ] == "2: second"
        assert (await call("str_replace", path="hello.txt", old_str="second", new_str="updated"))[
            "ok"
        ]
        assert (await call("insert", path="hello.txt", insert_line=0, new_str="# demo"))["ok"]
        expected = "# demo\nfirst\nupdated\n"
        assert (workspace / "hello.txt").read_text(encoding="utf-8") == expected
        source = (
            "from pathlib import Path; "
            f"assert Path('hello.txt').read_text(encoding='utf-8') == {expected!r}; "
            "print('verified')"
        )
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(source)}"
        executed = await call("run_command", command=command)
        assert executed["ok"] and executed["data"]["exit_code"] == 0
        assert executed["data"]["stdout"] == "verified\n"
        assert (await call("create", path="hello.txt", file_text="overwrite"))["error"][
            "code"
        ] == "ALREADY_EXISTS"
        assert (await call("view", path="../outside.txt"))["error"][
            "code"
        ] == "PATH_OUTSIDE_WORKSPACE"
        assert (await call("run_command", command="rm -rf protected"))["error"][
            "code"
        ] == "COMMAND_DENIED"
        assert (workspace / "hello.txt").read_text(encoding="utf-8") == expected
    print("tool demo finished: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
