# 工具系统（M2）

M2 提供独立可调用的文件系统、文本编辑和 Bash 工具，共 7 个。工具使用 LangChain `BaseTool` 接口，
支持 `invoke` / `ainvoke`；`run_command` 是异步工具，必须使用 `await ...ainvoke(...)`。
工具描述与 pydantic 参数 schema 为英文，结果为 JSON 文本。M3 再将这些工具接入 Agent 循环与
`mca run`，M5 接入 TUI 确认框；目前可以通过 Python API 或离线 demo 使用。

## 1. 离线运行

```bash
make demo-tools
make check
```

`make demo-tools` 在临时工作区依次执行创建、目录树、glob、范围查看、替换、插入与 Bash 文件检查，
断言文件内容与退出码；还验证创建冲突、越界拒绝和危险命令默认拒绝。无需模型配置或 API Key，
不调用网络，退出时清理临时目录；最后打印 `tool demo finished: all assertions passed`。

下面是可以直接运行的最小 Python 示例；输出为 `1: hello`：

```python
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from minimum_coding_agent.config.settings import Settings
from minimum_coding_agent.tools.defaults import create_tool_registry


async def main():
    with TemporaryDirectory(prefix="mca-example-") as directory:
        registry = create_tool_registry(Settings(workspace=Path(directory)), environ={})
        created = json.loads(await registry.get("create").ainvoke(
            {"path": "hello.txt", "file_text": "hello\n"}
        ))
        assert created == {"ok": True, "data": {"path": "hello.txt", "bytes_written": 6}}
        viewed = json.loads(await registry.get("view").ainvoke({"path": "hello.txt"}))
        assert viewed["ok"] and viewed["data"]["total_lines"] == 1
        print(viewed["data"]["content"])


asyncio.run(main())
```

正式装配时，`create_tool_registry(settings)` 默认捕获当前进程的环境快照；测试可传 `environ={}`
完全隔离环境。`registry.tools()` 返回可交给 `model.bind_tools(...)` 的工具列表。
以完整 `{"type":"tool_call","id":"...","name":"...","args":{...}}` 调用时，LangChain 返回
保留原始 `tool_call_id` 的 `ToolMessage`，其 `content` 为同一 JSON 协议。

## 2. 工具清单与参数

所有路径相对工作区根解析；也接受解析后仍位于工作区内的绝对路径。
未知参数、错误类型（如把字符串当行号）返回 `INVALID_ARGUMENT`。

| 工具集 | 名称与参数 | 成功时的 `data` 与边界 |
|---|---|---|
| filesystem | `tree(path=".", max_depth=None)` | `path`、`entries[{path,type,depth}]`、可读 `tree`、生效的 `max_depth`、`truncated`；目录深度从 1 起，调用深度不能超过配置上限 |
| filesystem | `glob_files(pattern)` | `files`（相对工作区根的路径）、`limit`、`truncated`；只匹配文件，支持 `*`、`?`、字符组和 `**` |
| editor | `view(path, view_range=None)` | 文件：`type="file"`、带 `N: ` 行号的 `content`、请求的 `start_line/end_line`、`total_lines`、`truncated`；目录：`type="directory"`、`entries[{name,type,size_bytes}]`、`truncated` |
| editor | `create(path, file_text)` | `path`、`bytes_written`；父目录必须已经存在，已存在的目标（包括悬空符号链接）绝不覆盖 |
| editor | `str_replace(path, old_str, new_str)` | `path`、`replacements=1`；`old_str` 必须非空且唯一，重叠匹配也算多次；新文本可为空 |
| editor | `insert(path, insert_line, new_str)` | `path`、`insert_line`；合法位置为 0 到文件行数，在该行之后插入，0 为开头；空文本是无操作 |
| bash | `run_command(command, timeout_seconds=None)` | `exit_code`、`stdout/stderr`、`stdout_truncated/stderr_truncated`、`timed_out`；调用超时不能超过配置上限 |

`glob_files("*.py")` 只匹配工作区根，`glob_files("**/*.py")` 匹配根和各级子目录。
glob 不接受绝对路径、`..` 路径分量或 NUL。匹配结果上限使用 `filesystem.max_entries`，
遍历深度不受 `tree` 的深度上限影响。

`view_range=[start,end]` 为 **1 起始闭区间**；`[10,-1]` 表示第 10 行直到末尾。
显式范围必须落在现有行内，空文件无范围查看返回空内容和 `total_lines=0`。目录不接受范围，
只列直接子项，递归结构使用 `tree`。文件内容超出输出上限时标注截断，
`start_line/end_line` 仍表示请求范围；缩小范围后可以继续查看。

编辑仅支持 UTF-8 文本，含 NUL 或非法 UTF-8 的文件按二进制拒绝；普通文件以外的设备、FIFO 等被拒绝。
替换保留其余字节及 CRLF，插入在需要处补分隔换行（已有 CRLF 文件使用 CRLF），不自动为末尾插入补尾换行。
已有文件通过同目录临时文件与 `os.replace` 原子替换，并保留权限位；创建通过临时文件与 `os.link`
原子发布完整内容，即使发生并发创建也不覆盖。新文件权限为临时文件的 `0600`。
参数、匹配、大小校验和写入失败都不改变原文件，临时文件在操作后清理。

## 3. 配置与限额

完整示例见 [`config/agent.example.yaml`](../config/agent.example.yaml)。

| 配置 | 默认值 | 作用 |
|---|---|---|
| `tools.filesystem.enabled` / `editor.enabled` / `bash.enabled` | `true` | 关闭后不构建或暴露该工具集，其余工具保持可用 |
| `tools.filesystem.max_depth` | `3` | `tree` 最大深度，1–32；调用可降低上限 |
| `tools.filesystem.max_entries` | `2000` | `tree` / glob / 目录 `view` 的返回条目上限，至少 1 |
| `tools.filesystem.exclude_dirs` | `.git`、`.venv`、`.tools`、`.uv-cache`、`.uv-python`、`node_modules`、`__pycache__`、`dist`、`build` | 遍历时跳过的目录名 |
| `tools.editor.max_file_size_kb` | `1024` | 文件读取、创建和编辑后内容的字节上限，按 1024 bytes/KB 计算，至少 1 |
| `tools.editor.max_output_chars` | `20000` | 文件 `view` 内容字符上限，含截断标记，至少 1000 |
| `tools.bash.timeout_seconds` | `120.0` | 命令超时上限，秒；必须大于 0 |
| `tools.bash.max_output_chars` | `20000` | stdout / stderr **分别**最多保留的字符数，含头尾之间的截断标记，至少 1000 |
| `tools.bash.confirm_dangerous_commands` | `true` | 命中危险规则后先调用异步确认钩子；没有钩子时拒绝 |

`todo/search/code` 的配置结构已存在，但其工具分别属于 M4/M7，M2 不构建这些工具。
排除目录仅影响发现与列表，不是访问控制：显式 `view(".git/config")` 仍由工作区护栏判定。
目录树、glob 和目录查看跳过解析到工作区外或无法解析的符号链接；内部目录链接可列出但不递归，避免环。

## 4. 结果与错误语义

成功结果：`{"ok":true,"data":...}`。
失败结果：`{"ok":false,"error":{"code":"...","message":"...","hint":"..."}}`。
Bash 非零退出或超时时，失败结果还包含顶层 `data`，保留同样的退出码、输出与标记供下一轮决策。
工具参数与业务错误不抛给运行时；未预期异常转成 `INTERNAL_ERROR`，日志只记录工具名与异常类型，
不输出原异常文本或参数。`asyncio.CancelledError` 继续传播，Bash 会先清理进程组。

| `error.code` | 含义与处理 |
|---|---|
| `INVALID_ARGUMENT` / `INVALID_RANGE` | 参数 schema 或范围错误；按工具描述修正 |
| `PATH_OUTSIDE_WORKSPACE` / `INVALID_PATH` | 路径越界或不可解析；使用工作区内路径 |
| `NOT_FOUND` / `NOT_FILE` / `NOT_DIRECTORY` | 目标不存在或类型不合适 |
| `ALREADY_EXISTS` | 创建冲突；选择新路径或使用编辑工具 |
| `MATCH_NOT_FOUND` / `MATCH_NOT_UNIQUE` | 替换无法唯一定位；先 `view` 并增加精确上下文 |
| `BINARY_FILE` / `FILE_TOO_LARGE` | 不支持的文本或大小超限；选 UTF-8 文件或调整限额 |
| `PERMISSION_DENIED` / `IO_ERROR` | 权限或系统 I/O 错误，原始系统异常文本不暴露 |
| `COMMAND_DENIED` | 危险命令未获得确认，命令没有启动 |
| `COMMAND_FAILED` / `TIMEOUT` | 查看 `data.exit_code/stdout/stderr/timed_out` 后决策 |
| `ASYNC_REQUIRED` | 对异步命令工具误用同步调用；改用 `await tool.ainvoke(...)` |
| `INTERNAL_ERROR` | 未预期异常或不可序列化的返回值；检查日志 |

注册错误是启动期错误：不合法的工具集、重复工具集或重名工具抛出 `ToolRegistrationError`，
并指出冲突名称；注册整批失败时，先前工具保持不变，不留下本批的部分工具。

## 5. Bash 确认与安全边界

`create_tool_registry(settings, confirm_command=...)` 接受 `async (command: str) -> bool`
回调：`True` 执行，`False` 拒绝。M2 没有 UI 依赖，无回调时危险命令默认拒绝；M5 再接确认对话框。
也可给 `BashToolset(policy=...)` 提供自定义 `BashPolicy.should_confirm(command)` 实现。

默认策略识别递归 `rm`（包含短选项组合、长选项和带路径的命令）、`git reset --hard`、
`git clean` 的强制选项、`sudo`、`mkfs`、`dd`，以及 `eval/source`、命令替换与常见 `shell -c` 包装。
这些是启发式规则，复杂 shell 语法可能绕过或触发保守确认；关掉确认开关会允许其直接执行。

Bash 使用 `/bin/bash` 非交互执行，stdin 关闭，cwd 固定为工作区根；stdout/stderr 持续并发读取，
只保留有界头尾，避免输出量无限增长。命令超时或取消时终止整个进程组并等待 shell 退出，
正常结束也清理同组后台进程，不支持启动长期驻留服务。

传给 Bash 的环境会剥离 `MCA_API_KEY`、配置的 `provider.api_key_env`，以及名称中含
`API_KEY/APIKEY/TOKEN/SECRET/PASSWORD/CREDENTIAL/PRIVATE_KEY/ACCESS_KEY` 等模式的变量，
包括 `MCA_LIVE_API_KEY` 与常见厂商密钥；还剥离配置中 MCP server 的 `env` 名称，
以及非交互 shell 启动钩子 `BASH_ENV/ENV/SHELLOPTS/BASHOPTS`。调用方环境映射不被修改。
已知密钥值会在结果文本中遮蔽为 `***REDACTED***`。

**安全边界**：文件工具的护栏是路径规范化与包含检查，Bash 只提供 cwd、确认、超时与输出限制，
不是操作系统沙箱。shell 能使用绝对路径访问外部文件、运行解释器或创建新会话；进程组清理不保证
终止主动脱离组的程序。路径护栏也不防御恶意进程在校验与访问之间并发替换路径。
强隔离需要外部沙箱/容器；这些边界与 `design.md` D4 的 MVP 取舍一致。

## 6. 扩展契约

新增工具集实现 `name: str` 和 `build(ctx: ToolContext) -> list[BaseTool]`，使用 LangChain `@tool`
与 pydantic 参数模型（可继承 `ToolArguments`）生成 schema。原始工具返回 JSON 可序列化的 Python 数据，
预期失败抛出 `ToolError(code, message, hint)`，不要自行重复包装 `ok/data`。
通过 `ToolRegistry(ctx).register(toolset, enabled=...)` 注册后，共用结果包装、脱敏和重名检查。
工具名也会与 `mcp__<server>__<tool>` 这类完整名称一起进行精确冲突检查。

工具集只依赖配置与能力层，不导入 Agent/UI/CLI；注册新工具集即可向模型暴露描述与参数，
无需修改模型 provider。契约、配置开关与 `ToolMessage` 行为由
`tests/unit/test_tool_registry.py`、`test_tool_defaults.py` 覆盖，边界场景由各工具单测覆盖。
