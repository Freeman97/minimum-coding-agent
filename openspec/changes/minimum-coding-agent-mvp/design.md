# Design

## Context

见 [proposal.md](proposal.md) 的 Why 与 What；行为契约见 `specs/` 下 9 个 capability。本文件只回答"如何实现"。

当前仓库除 [README.md](../../../README.md) 与 OpenSpec 骨架外为空，属 greenfield。设计必须同时满足以下环境约束：

- 运行环境：Ubuntu 22.04、系统 Python 3.10.6、**无 pip/uv/ripgrep**；Node 24 + npm 可用；pypi/github 可访问。
- 文件写入被限制在工作区内（DSH workspace-write 沙箱），因此工具链、依赖、虚拟环境、Python 解释器都必须目录本地化。
- 学习目的：实现应可读、模块边界清晰、避免过度抽象；用显式代码展示 ReAct 与工具循环，而不是调用隐藏循环的黑盒封装。
- 交付方式：M0–M9 分模块实现，每模块完成后暂停人工 Review（见"交付流程"）。

## Goals / Non-Goals

**Goals:**

- 用 10 个可独立验证的模块（M0–M9）覆盖 proposal 中全部 capability，模块间依赖单向、可逐模块 Review 与回滚。
- 单 Agent、显式 LangGraph `StateGraph` 的 ReAct 循环；控制台与 headless 共享同一运行时与事件流。
- 所有模块的自动化测试可离线运行（脚本化模型 + 临时工作区 + 替身 MCP server）；真实模型测试按需启用。
- 分模块逐层引入依赖：后续模块不污染前面模块的依赖面。
- 工程规范（Google Style docstring、质量门禁、模块 Definition of Done）可被机械检查。

**Non-Goals（设计层面额外边界）:**

- 不做容器级/进程级沙箱：Bash 工具只提供工作目录、超时、截断与危险命令确认，**不承诺阻止任意系统访问**（见 Risks）。
- 不做会话持久化、断点恢复、多 Agent 协作、Web UI、Windows 终端适配。
- 不实现联网检索、LSP/类型推断、多语言代码定位（只保留语言提取器注册架构）。
- 不做 Theme 模块与主题切换：控制台只保留最小布局样式，仅保证可用性与可测试性；不做 i18n。
- 不支持 Windows 终端：MVP 仅面向 Linux/macOS 终端。
- 不为将来 Provider 预写 Anthropic 适配器，只定义注册契约与文档。

## 总体架构

分层与依赖方向（上层依赖下层，禁止反向依赖）：

```
+------------------------------------------------------------------+
| 入口层     cli.py / ui/ (Textual)         headless renderer       |
+-----------------------------+------------------------------------+
                              | AgentEvent 流
+-----------------------------v------------------------------------+
| 运行时层   agent/runtime.py  graph.py  prompts.py  events.py     |
|            todo 状态（agent/state.py）                            |
+-----------------------------+------------------------------------+
                              |
+-----------------------------v------------------------------------+
| 能力层     llm/ (provider 工厂)      tools/ (工具集)              |
|            codeintel/ (Python 提取器) extensions/ (命令/指令/MCP) |
+-----------------------------+------------------------------------+
                              |
+-----------------------------v------------------------------------+
| 装配层     app.py（composition root）  config/（Settings+加载）    |
+------------------------------------------------------------------+
```

- **单向依赖**：`ui/`、`cli.py` 只依赖 `agent/` 的事件与运行时接口以及 `config/`；`agent/` 依赖 `llm/`、`tools/`、`codeintel/`（间接通过工具集）；`tools/` 与 `extensions/` 不依赖 UI。任何模块都不允许 import 入口层。
- **composition root**：`app.py` 负责按配置装配 provider、工具集、运行时、UI/headless，是唯一知道所有具体实现的位置。测试可在不启动 UI 的情况下装配同一条链路。

## Decisions

### D1 仓库布局与包结构

```
minimum-coding-agent/
├── pyproject.toml / uv.lock / Makefile / .gitignore
├── README.md / AGENT.md
├── config/agent.example.yaml
├── docs/conventions.md
├── scripts/bootstrap.sh           # 项目内安装 uv（M0）
├── src/minimum_coding_agent/
│   ├── __main__.py / cli.py
│   ├── app.py                     # composition root
│   ├── config/{settings,loader}.py
│   ├── llm/{base,registry,openai_compatible}.py
│   ├── tools/{base,workspace,filesystem,editor,bash,todo,search,code}.py
│   ├── agent/{state,events,prompts,graph,runtime,context}.py
│   ├── codeintel/{base,registry,python_extractor}.py
│   ├── extensions/{commands,instructions,mcp_loader}.py
│   └── ui/{app,worker,messages,styles.tcss,widgets/*.py}
└── tests/{unit,integration,ui,live,fixtures}/
```

理由：按能力而非框架分组，模块边界与 Review 门禁一一对应；`tree-sitter`、MCP 等重依赖分别被隔离在 `codeintel/` 与 `extensions/mcp_loader.py`，便于后续替换。

### D2 模块划分与依赖顺序

| 模块 | 内容 | 依赖 | 规模 |
|---|---|---|---|
| M0 | 工程地基与配置（uv/pyproject/src 布局、Settings+加载、日志、CLI 骨架、质量门禁） | - | S |
| M1 | 模型接入层（Provider 协议/注册/OpenAI 兼容/脚本化模型/live smoke） | M0 | S |
| M2 | 工具系统与基础工具（Registry/路径护栏/文件/编辑/Bash） | M0 | M |
| M3 | Agent 核心（StateGraph/Prompt/多轮/事件流/headless `run`） | M1,M2 | L |
| M4 | 规划与 TODO（状态、工具、提示约束） | M3 | S |
| M5 | Console UI（Textual App/组件/取消与确认；无 Theme） | M3,M4 | L |
| M6 | 扩展机制（`/` 命令、AGENT.md） | M3,M5 | M |
| M7 | 代码智能（文本检索 + Python 定位 + 多语言注册架构） | M2 | M |
| M8 | MCP 集成（配置/加载/命名空间/失败隔离） | M2,M6 | M |
| M9 | 整合与交付（E2E、live e2e、错误打磨、文档、归档） | 全部 | M |

里程碑：**A**=M0–M3（headless agent 可完成一次真实编码任务）、**B**=M4–M5（TUI 可用）、**C**=M6–M8（README 功能全覆盖）、**D**=M9（交付）。

### D3 模型接入层

- **抽象**：`ChatModelProvider` 协议，唯一职责是"把配置转换成 LangChain `BaseChatModel`"。Agent 运行时、工具、UI 只依赖 `BaseChatModel`，不感知具体厂商。
- **MVP 实现**：`OpenAICompatibleProvider`，基于 `langchain-openai` 的 `ChatOpenAI`，支持自定义 `base_url`、`api_key`、`model`、`temperature`、`max_tokens`、`timeout`。这是 README 要求的"暂只支持 OpenAI 格式"。
- **扩展点**：`ProviderRegistry` 以名称注册（`openai-compatible`）；新增 Anthropic 只需新增 provider 模块并注册，不改运行时。注册契约写入 `docs/conventions.md`，并用一个测试用 provider 验证契约。
- **脚本化模型**：测试专用 `ScriptedChatModel(BaseChatModel)`，按预置脚本返回 `AIMessage`（含 `tool_calls`）或流式片段。生产代码不感知该实现，符合 spec 的"可脚本化测试"。
- **替代方案**：直接用 OpenAI SDK 自行封装 → 放弃 LangChain 消息/工具调用生态，成本更高；使用 LangChain 1.x 的 `create_agent` 高阶封装 → 隐藏 ReAct 循环，不利于学习。

### D4 工具系统

- **Toolset 协议**：`name` + `build(ctx: ToolContext) -> list[BaseTool]`。工具使用 LangChain `@tool` + pydantic 参数模型生成 JSON Schema，工具描述与参数说明用英文（模型可见）。
- **Registry**：合并所有启用工具集的工具；启动期检测重名（含 MCP 命名空间前缀）并失败；支持按配置启用/禁用工具集。
- **统一结果协议**：所有工具返回 JSON 文本 `{"ok": true, "data": ...}` 或 `{"ok": false, "error": {"code", "message", "hint"}}`；包装器捕获可预期错误与未预期异常，统一转换为 `ToolMessage`，保证循环不中断（spec: tool-system / 工具失败语义）。
- **路径护栏**：`WorkspaceGuard.resolve(path, must_exist)` 以工作区根为基准解析，`resolve()` 后校验 `is_relative_to(root)`，拒绝绝对路径逃逸、`..`、符号链接逃逸与工作区外写入；错误带修复提示。
- **内置工具清单**（模型可见名称）：

| 工具集 | 工具 | 关键参数 | 说明 |
|---|---|---|---|
| filesystem | `tree` | `path=".", max_depth=3` | 递归目录树，跳过排除目录，深度/条目上限 |
| filesystem | `glob_files` | `pattern` | 工作区内 glob，结果上限 |
| editor | `view` | `path, view_range=None` | 文件：1 起始行号，`[start,end]` 闭区间，`end=-1` 到文件末尾；目录：列直接子项 |
| editor | `create` | `path, file_text` | 创建新文件，已存在则报错不覆盖 |
| editor | `str_replace` | `path, old_str, new_str` | 唯一精确替换，0/多次命中则报错不修改 |
| editor | `insert` | `path, insert_line, new_str` | 在指定行后插入，`insert_line=0` 表示文件开头，越界报错 |
| bash | `run_command` | `command, timeout_seconds=None` | 非交互、工作目录、超时、输出头尾截断 |
| todo | `write_todos` | `todos[]` | 返回 `Command` 更新会话状态 |
| search | `search_text` | `query, path=".", glob=None, regex=False, case_sensitive=False, max_results=50` | 工作区文本检索 |
| code | `code_outline` / `find_definition` / `find_references` | `path` / `name, path="."` | 委托 `codeintel/`，工具层不做解析 |

- **文本编辑语义**：对齐 Claude text editor 的四类工具（`view`/`create`/`str_replace`/`insert`，MVP 不含 `undo_edit`）。行号从 1 开始；`view_range` 为闭区间且 `end=-1` 表示读到文件末尾（仅文件）；`insert_line` 表示"在该行之后插入"，0 表示文件开头；所有编辑要么完整成功要么不修改文件。文件系统工具集只保留 `tree`/`glob_files`，目录的直接子项由 `view` 展示、递归结构由 `tree` 展开。
- **Bash 安全**：`asyncio.create_subprocess_shell` + `start_new_session=True`，超时 `killpg`；stdout/stderr 各保留头尾并标注截断；剥离已知密钥环境变量（如 `MCA_API_KEY`、provider key 环境变量）后再传递环境；危险命令模式（`rm -rf`、`git reset --hard`、`git clean -fd`、`sudo`、`mkfs`、`dd` 等）通过 `BashPolicy.should_confirm()` 判定，TUI 弹确认框，headless 默认拒绝。
- **替代方案**：每个工具手写 JSON Schema → 重复且易错；直接暴露 Python 函数给模型 → 无参数校验。`@tool` + pydantic 是 LangChain 生态的最小标准做法。

### D5 Agent 运行时

**图结构**（LangGraph `StateGraph`，显式节点与条件边）：

```
        +---------+
START ->|  agent  |<-------------+
        +----+----+              |
             |                   |
   有 tool_calls 且未达上限       |
             v                   |
        +---------+              |
        |  tools  |--------------+
        +---------+
             |
   无 tool_calls -> END
   达到迭代上限 -> END（RunFinished.reason="max_iterations"）
```

- **状态**：

```python
class TodoItem(TypedDict):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed"]

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    todos: list[TodoItem]
    iterations: int
```

- **agent 节点**：先运行上下文压缩管线（见 D7），再调用绑定了工具的模型；流式 token 通过 `astream(stream_mode=["messages", "updates"])` 转发为 `TokenDelta`；`iterations += 1`。
- **tools 节点**：LangGraph `ToolNode`。`write_todos` 通过返回 `Command(update={"todos": ...})` 更新状态；运行时从 `updates` 流中识别 `todos` 变化并发布 `TodosUpdated`。若当前 LangGraph 版本对工具返回 `Command` 支持不可靠，则退化为"工具写回消息 + 后置 TODO 同步节点"（M3/M4 实现时验证，属于实现细节，不改变 spec）。
- **多轮会话与 Checkpoint 扩展点**：checkpointer 是图编译参数而非图节点；运行时通过 `CheckpointBackend` 抽象管理会话状态，MVP 实现内存后端（`MemorySaver`），每次会话一个 `thread_id`，`/clear` 生成新 `thread_id`。持久化后端（SQLite/文件）只需新增 backend 实现并在装配处选择，Agent 图、工具与 UI 不变；MVP 不实现持久化与断点恢复 UX（完整成本见 Risks）。上下文压缩是运行时职责，不属于模型 provider。
- **迭代上限**：`agent.max_iterations`（默认 30）写入状态比较；达到上限时结束并向用户说明，而不是抛异常。
- **Prompt 装配**（`agent/prompts.py`）：按固定顺序拼接节段——`ROLE`、`ENVIRONMENT`（工作区/OS/日期/模型名）、`PROJECT_INSTRUCTIONS`（AGENT.md 内容）、`TOOL_POLICY`（先读后改、优先检索、修改后验证、失败自我纠正）、`PLANNING`（TODO 规则）、`RESPONSE_STYLE`。动态值用显式转义拼接而非 `str.format`，避免 AGENT.md 中的花括号破坏模板。
- **事件流**（`agent/events.py`，frozen dataclass）：

```python
RunStarted(run_id, user_input)
TokenDelta(text)
AssistantMessage(text)
ToolCallStarted(tool_call_id, name, args_summary)
ToolCallFinished(tool_call_id, name, status, result_summary)
TodosUpdated(todos)
RunFinished(run_id, reason: Literal["completed","cancelled","max_iterations","error"])
AgentError(message, where: Literal["model","tool","runtime"], retryable)
```

- **取消**：运行时暴露异步迭代器；调用方（Textual worker）取消任务时关闭生成器，`RunFinished.reason="cancelled"` 由运行时保证发出。headless 渲染器把事件打印为人类可读文本，并复用同一运行时。
- **替代方案**：`create_react_agent` 预构建 → 隐藏循环细节且 API 随版本变动；自研 while 循环不用 LangGraph → 偏离 README 技术栈、失去 checkpointer/流式能力。

### D6 规划与 TODO

- TODO 是**会话状态**的一部分（`AgentState.todos`），不是文件；保证多轮保留、新会话清空、/todos 可读，且与 UI 通过 `TodosUpdated` 事件解耦。
- `write_todos` 接收完整列表（整体替换，语义简单，避免增量合并的歧义）；校验 id 唯一、非空、状态枚举、内容长度；非法输入返回结构化错误且不改变状态。
- 提示词只约束行为（先计划、最多一个进行中、及时收尾），不做硬校验（例如不强制必须有 in_progress）；以便模型在单步任务中直接作答。
- UI 的 TODO 面板只消费事件与运行时快照，不负责规划逻辑。

### D7 会话上下文管理

上下文管理采用**可组合压缩管线**，机械裁剪只作为最后兜底：

- 协议：`ContextCompressor`（`name` + `async compress(messages, budget, ctx)`），`ContextPipeline` 按配置顺序执行；`agent/context.py` 提供注册表与装配。
- 内置压缩器：
  - `ToolOutputTruncator`：截断过大的历史工具输出（保留头尾与摘要），不删除消息；
  - `LlmSummarizer`：将较早的对话轮次交给同一模型总结为一条摘要消息，保留系统提示与最近 N 轮；默认关闭，避免 MVP 阶段的额外 API 成本与不确定性；
  - `WindowDropper`：按完整轮次丢弃最早消息（保证 tool_call 与 ToolMessage 配对），作为**最后兜底**，保证任何情况下都能收敛到预算内。
- 预算：`agent.context.max_tokens`（默认 64k，保守）；达到软阈值先运行非破坏性压缩器，仍超预算再触发兜底；压缩后追加一条简短说明"更早内容已压缩"，不向用户暴露内部细节。
- 失败处理：任一压缩器异常或超时 → 记录日志并跳过，继续执行后续压缩器；最终由兜底保证预算。
- 测试：机械压缩器用构造消息测试；`LlmSummarizer` 用 `ScriptedChatModel` 做离线测试（摘要内容、保留最近轮次、配对完整）；管线失败回退测试。
- 替代方案：固定 `trim_messages` 单一策略 → 不可组合、无法引入 LLM 摘要；纯 LLM 压缩 → 成本与不确定性高，必须有机械兜底。

### D8 Console UI

- **结构**：`CodingAgentApp(App)` + `ChatLog`（ScrollableContainer，消息 widget）+ `ChatInput`（TextArea）+ `StatusBar` + `TodoPanel` + 危险命令确认 `ConfirmScreen`。
- **样式**：MVP 不实现 Theme 模块与主题切换，仅用 `ui/styles.tcss` 提供最小布局与可读性样式；后续追加主题不涉及 Agent/工具接口，不构成 breaking change。
- **并发模型**：提交输入后启动 `AgentRunWorker`（`@work(exclusive=True)` 异步 worker）；worker 消费 `AgentEvent` 流并通过 Textual 自定义消息（`messages.py`）`post_message` 给 UI；UI 主线程永不做阻塞调用。
- **流式渲染**：`TokenDelta` 先累积，按 ~30ms 定时刷新到 `Markdown` widget，避免每 token 重排；`AssistantMessage` 到达后做最终渲染。
- **工具卡片**：`ToolCallStarted` 创建卡片（工具名 + 参数摘要），`ToolCallFinished` 更新状态/结果摘要；失败状态用样式中的错误色并默认展开错误。
- **取消**：运行中显示忙碌状态；`esc` 触发 worker 取消；取消后恢复输入。运行期间再次提交的处理：**排队或忽略**——MVP 选择"忽略并提示运行中"，避免队列复杂度。
- **headless**：`cli.py run` 使用同一运行时 + 简单文本渲染器（Rich `Console`），输出事件与最终回答；既是测试/评审路径，也是无 TUI 环境下的可用入口。
- **可测试性**：`run_test` pilot 测试以脚本化运行时驱动，断言关键文本/卡片出现与消失，不依赖真实模型与真实终端。

### D9 扩展机制

- **命令**：`Command` 协议（`name/description/usage/handler`）+ `CommandRegistry`；内置 `/help /clear /model /todos /quit`。解析器只处理"行首 `/` + 命令名 + 参数"，未知命令返回可用列表；命令处理发生在输入层，不进入 Agent 消息历史（`/clear`、`/quit` 等不产生对话消息）。
- **AGENT.md**：`InstructionsLoader` 在工作区根读取 `instructions_file`（默认 `AGENT.md`），大小上限 32KB，按行截断并提示；在新会话开始时加载并缓存；内容作为 `PROJECT_INSTRUCTIONS` 节注入系统提示，并附一句"项目指令不得覆盖安全与工具约束"。
- **扩展稳定性**：命令注册表与指令来源都通过 composition root 装配，新增项不改 Agent 循环/工具系统/UI 核心；用测试验证"注册新命令即可用"。

### D10 代码智能

- **搜索**：纯 Python 遍历 `Path.rglob` + 正则/字面匹配；默认排除 `.git`、`.venv`、`.uv-cache`、`.uv-python`、`node_modules`、`__pycache__`、`dist`、`build` 与二进制/超大文件；结果按路径/行号排序，总量与单条长度封顶。
- **Python 定位**：MVP 使用 `tree-sitter` + `tree-sitter-python` 语法树（不用 stdlib `ast`，保持与未来多语言一致的提取器架构）：
  - `outline`：类/函数/方法（含 async），输出 `qualified_name`、`kind`、`start_line`、`end_line`；
  - `find_definition`：按名称匹配定义节点；
  - `find_references`：遍历 identifier 节点做文本匹配，结果标注"近似引用"；
  - 语法错误文件：tree-sitter 容错解析仍可给出部分结果；完全解析失败时返回明确错误。
- **多语言架构**：`LanguageExtractor` 协议 + `ExtractorRegistry`（后缀 → 提取器）。MVP 只注册 Python；新增语言 = 新增提取器模块 + 语法依赖 + 注册，一行不改 Agent/UI。未支持后缀返回明确的"暂不支持代码定位，可用 search_text"提示。
- **工具封装**：`tools/code.py` 只做参数校验、路径护栏、结果截断与格式化；解析逻辑全在 `codeintel/`，便于单测与未来替换。
- **替代方案**：stdlib `ast` → 仅 Python、零依赖，但与多语言架构不一致且需两套代码路径；`ripgrep` → 系统无 rg 且引入外部二进制；LSP → 超出 MVP。

### D11 MCP 集成

- **配置与传输扩展点**：`mcp.servers[]`（`name/transport/command/args/env/enabled`）；transport 经注册表解析，MVP 只注册 `stdio`，流式 HTTP/SSE 后续通过新增 transport 接入，不修改 loader/Agent/UI；启动时校验并给出错误项。
- **加载**：`extensions/mcp_loader.py` 使用 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 作为薄封装（隐藏第三方 API 细节），把返回工具包装为带命名空间 `mcp__<server>__<tool>` 的 LangChain 工具；名称冲突在 Registry 层检测。
- **生命周期**：在 composition root 启动时异步加载，收集每个服务器的失败为 warning；应用退出时关闭所有连接/子进程。加载失败不影响内置工具与应用启动。
- **调用**：工具参数结构由 MCP server 声明生成；参数校验失败在本地拦截；远端错误/超时转换为工具结果错误返回模型。
- **可验证**：`tests/fixtures/mcp_echo_server.py` 用官方 `mcp` SDK 实现的标准输入/输出替身服务器（提供 echo 工具与一个故意失败的服务器），测试离线运行；真实 server 通过配置接入验证。
- **替代方案**：手写 JSON-RPC → 重复官方 SDK 工作；不隔离服务器失败 → 一个坏配置拖垮整个应用。

### D12 配置模型

- **pydantic v2 Settings**（分层校验、错误定位、默认值）：
  - `provider`: `name`、`base_url`、`api_key` 或 `api_key_env`（二选一）、`model`、`temperature`、`max_tokens`、`timeout_seconds`。
  - `workspace`、`instructions_file`。
  - `agent`: `max_iterations`、`context.{max_tokens, compressors[], llm_summary_threshold_tokens}`。
  - `tools.{filesystem,editor,bash,todo,search,code}`：enabled + 各自上限/超时/排除目录/危险命令确认开关。
  - `mcp.servers[]`。
- **加载优先级**：CLI 参数 > 环境变量 > YAML 文件 > 内置默认值。环境变量使用显式映射（`MCA_BASE_URL`、`MCA_API_KEY`、`MCA_MODEL`、`MCA_CONFIG`、`MCA_WORKSPACE`），不做泛化嵌套覆盖，避免隐式行为。
- **密钥**：优先 `api_key_env`；允许 `api_key` 但启动时警告；日志/错误/事件中统一脱敏。
- **示例配置**：默认按 DeepSeek 端点占位（`base_url: https://api.deepseek.com`、`model: deepseek-chat`，实际端点/模型/环境变量名由用户后续提供），同时保留 Ollama 注释示例；不含明文密钥。

### D13 工程与质量规范（项目级）

- **代码**：英文标识符与注释；公开 API 必须有类型标注。
- **Docstring**：公开模块/类/公开函数/公开方法/Protocol 使用 **Google Style**（`Args:` / `Returns:` / `Raises:` / `Yields:` 按需）；私有函数一行摘要；测试代码豁免。这是硬性规范。
- **机械强制**：`pyproject.toml` 配置 ruff，启用 `D` 规则族并设置 `pydocstyle.convention = "google"`；`pydoclint` 校验 Args/Returns 一致性；`tests/**` 通过 per-file-ignores 豁免 D 规则。
- **质量命令**：`make setup`（项目内安装 uv + Python 3.12 + 依赖）、`make check`（ruff + pydoclint + pytest）、`make test-live`（`pytest -m live`）、`make run`（TUI）、`make demo`（headless 端到端 demo）。
- **Naming/commit**：分支 `feat/mX-<topic>`，Conventional Commits（`feat(m2): ...`），一个模块一个可 review 的 PR 式分支；通过 Review 后合并到 `master`。
- **规范落点**：`docs/conventions.md`（规范正文）+ `AGENT.md`（Agent 自举约束）+ `openspec/config.yaml`（产物与 apply 门禁约束）。

### D14 测试策略

| 层级 | 方式 | 覆盖 |
|---|---|---|
| 单元 | pytest + tmp_path | 配置加载/优先级/校验、provider 工厂、路径护栏、每个工具、命令注册、AGENT.md、搜索/定位、MCP 配置校验 |
| Agent 集成 | `ScriptedChatModel` | ReAct 循环、工具回注、迭代上限、多轮、上下文压缩（含 LLM 摘要与兜底）、事件序列、TODO 状态 |
| UI | Textual `run_test` pilot | 提交/流式渲染/工具卡片/TODO 面板/取消/错误呈现 |
| MCP | stdio 替身服务器 | 加载、命名空间、调用、失败隔离、退出清理 |
| live（可选） | `pytest -m live`，env 均存在才运行 | M1 端点 smoke（流式）；M9 真实编码任务 E2E（临时工作区修 bug 跑测试） |
| 质量 | ruff + pydoclint + pytest | 每个模块的 Definition of Done |

- 默认 `pytest` 排除 live（`addopts = "-m 'not live'"`）；离线测试不得依赖网络。
- 关键断言优先验证**事件序列与工作区副作用**（文件内容变化、测试退出码），而不是内部实现细节。

### D15 依赖与工具链（工作区本地化）

- `scripts/bootstrap.sh` 把 uv 固定版本安装到 `.tools/`，并设置：`UV_INSTALL_DIR=.tools`、`UV_CACHE_DIR=.uv-cache`、`UV_PYTHON_INSTALL_DIR=.uv-python`、`UV_PROJECT_ENVIRONMENT=.venv`；`Makefile` 每条目标显式导出这些变量。
- `uv python install 3.12` → `uv sync`；所有依赖与版本锁在 `uv.lock`。若 3.12 下载不可用，回退系统 3.10（已验证所列依赖均支持 ≥3.10），并在 README 记录差异。
- 依赖按模块增量加入：M0 只加基础依赖；M1 加 `langchain-openai`；M7 加 `tree-sitter`/`tree-sitter-python`；M8 加 `mcp`/`langchain-mcp-adapters`。
- `.gitignore` 覆盖 `.venv/`、`.tools/`、`.uv-cache/`、`.uv-python/`、`.env`、缓存目录。

### D16 交付流程、Review 门禁与跨会话交接

**会话边界**：一个模块一个新会话；本对话只完成总体设计，M0 在全新会话启动。新会话通过 `openspec instructions apply` 自动获得 proposal/specs/design/tasks 与 config 的 context/operationGuidance，再按需读取现有代码与 git 状态；**不依赖上一会话的聊天记录**。

```
[会话 N] openspec instructions apply（自动含 proposal/specs/design/tasks）
    -> 读当前模块 tasks 段、相关 Decision、D17 最近记录、git status/log
    -> 分支 feat/mx-* -> 实现 + 测试 -> make check + 模块 demo
    -> 输出评审包 -> 人工 Review
         |-- 需修改：本会话继续迭代 -> 重跑 -> 再 Review
         +-- 通过：写回产物（D17 / tasks；必要时 specs/design）-> 合并 master
                  -> 勾选 Review Gate -> 结束会话
[会话 N+1] 新会话重新 apply，自动读取刚写回的产物 -> 下一个模块
```

- **会话启动**：只实现指定模块，显式声明"不进入下一模块"；先读 `openspec instructions apply` 返回的 tasks 对应段、design 相关 Decision 与 D17 记录、相关 spec，以及 `git status/log`。
- **会话结束**：`make check` 全绿、模块 demo 通过；输出评审包；Review 通过后先将结论写回 `design.md` D17 与 `tasks.md`（新增工作立即补成任务；行为契约变化更新 `specs`；方案变化更新对应 Decision），再合并 master 并勾选 Review Gate。
- **评审包固定字段**：改了什么/为什么、对外接口或行为变化、如何运行 demo、测试与质量命令输出、已知限制/风险、建议 Review 重点。
- **Definition of Done（每模块）**：`make check` 全绿；模块 demo 可运行；无未解决的设计偏差；公开 API 有合规 docstring；评审包已提交；**评审结论已写回产物（D17/tasks，必要时 specs/design）**。
- **设计变更**：使用 `/openspec-update-change` 修订 design/specs/tasks（或直接编辑后 `openspec validate`），再改代码；禁止代码领先文档。注意 `openspec update` CLI 用于刷新生成的指令文件，不用于修订产物内容。
- **回滚**：模块未合并前丢弃分支即可；已合并可用 `git revert`；无数据迁移。

### D17 实现决策与偏差记录（跨会话交接）

跨会话只通过 change 产物、代码/测试与 git 交接；`design.md` 属于 apply 自动加载的 `contextFiles`，因此把"为什么/取舍/偏差"集中记录在本节。每个模块 Review 通过后、会话结束前追加一条（不超过 10 行），后续会话自动读取。

记录模板：

```markdown
#### Mx <模块名>

- 分支/提交：`feat/mx-*`，`<sha>`..`<sha>`
- 交付范围：...
- 与设计的偏差及原因：...（无则写"无"）
- 评审中定下的取舍：...
- 对后续模块的影响/前置条件：...（必须同步落到 tasks.md 任务或对应 Decision）
- 遗留问题/已知限制：...
```

规则：

- 只有"为什么/取舍/偏差"进本节；可执行项落到 `tasks.md`，行为契约变化改 `specs`，方案变化改对应 Decision（D1–D16）。
- 测试日志与完整 diff 留在会话评审包与 git commit，不写入本节，保持可读性与低噪声。
- 归档后本节随 change 进入 archive；需要长期保留的内容在 M9 提炼到 README/docs。
- 若某条交接信息会影响尚未开始的模块，必须**立即**更新该模块的 tasks 或 design 决策，不能只留在记录里。

#### M0 工程地基与配置

- 分支/提交：`feat/m0-foundation`，`7507237`..`2224153`（实现与评审前审计修复提交；D17/tasks 交接记录随后单独提交）
- 交付范围：项目内 uv/CPython 3.12/依赖工具链；strict pydantic Settings 与分层加载（CLI > MCA_* env > YAML > 默认）；密钥脱敏与启动前校验；`mca` CLI 骨架（TUI/`run` 占位、`--version/--help/--config/--workspace`、退出码 0/2/3/4）；ruff(D+Google)+pydoclint+pytest 质量门禁；示例配置、`docs/conventions.md`、`AGENT.md`。
- 与设计的偏差及原因：开发环境缺少 make 且 sudo 不可用，改用用户级 GNU make 4.3（不入库、不改系统目录）；uv installer 的 receipt 通过 `XDG_CONFIG_HOME` 落到 `.tools/config`，否则沙箱拒绝写 `~/.config`；网络实际可访问 astral.sh/PyPI，成功安装 uv 0.13.1 + CPython 3.12.15；代码保持 3.10 兼容基线（ruff `target-version="py310"`）以支持离线回退；design 中的 `app.py` composition root 按 M3/M5 任务延后，M0 不建空占位文件。
- 评审前独立验证修复（行为契约变化）：环境变量只识别显式 `MCA_*`（移除 pydantic-settings；裸 `BASE_URL`/`MODEL`/`API_KEY`/`WORKSPACE`/`CONFIG` 不再生效，`load_settings(environ=...)` 与进程环境完全隔离）；空/空白密钥与 provider 字符串按非法配置拒绝；`redacted_dict()` 遮蔽 `mcp.servers[*].env` 值；回归测试与文档已同步。
- 评审中定下的取舍：待人工 Review 后补充。
- 对后续模块的影响/前置条件：M1 直接消费 `Settings.provider` 与退出码契约（0/2/3/4 为稳定契约）；`MCA_API_KEY` 覆盖 YAML `api_key_env` 的语义已固化并写入 conventions；配置 schema 已含 tools/mcp 段，M2/M3/M7/M8 只能增量加键并同步示例与测试；`make test-live`/`make demo` 分别在 M1/M3 加入。
- 遗留问题/已知限制：make 需环境自备（本项目会话已用户级安装）；TUI/headless/模型/工具均为占位（对应 M1–M5）；DeepSeek 示例的 `base_url`/`model`/密钥变量名仍按 design Open Question 由用户最终确认；pydoclint 仅检查 `src` 且跳过私有函数。

## Risks / Trade-offs

- [LangGraph/LangChain 1.x API 变动] → 锁定依赖主版本；显式图与 `astream` 用法用集成测试覆盖；避免依赖高阶封装。
- [不同 OpenAI 兼容端点的工具调用能力差异] → provider 层只要求标准 Chat Completions + tool calls；live smoke 优先验证工具调用；配置可调 `max_iterations` 与超时；文档说明兼容性要求。
- [Bash 不是真正沙箱，可绕过工作区限制] → 明确写入文档与 UI 提示；危险命令确认 + 超时；未来可用容器/受限 shell 替换（扩展点在 `BashPolicy`）。
- [Textual 流式渲染性能与竞态] → worker 与 UI 线程隔离、增量 30ms 批量刷新、exclusive worker、`run_test` 覆盖取消/错误路径。
- [MCP server 卡死或协议不兼容] → 每服务器隔离加载 + 超时 + 退出清理；M8 用替身服务器测试；失败仅告警。
- [tree-sitter 语法包平台/版本问题] → 使用官方预编译 wheel 并锁版本；解析失败降级错误提示；MVP 只依赖 Python 语法包，减少风险面。
- [live 测试成本与不确定性] → 默认排除、显式 `-m live`、限制迭代/超时、使用临时工作区；不进入日常质量门禁。
- [上下文压缩误删关键信息或摘要偏差] → 保留系统提示与最近轮次、先做非破坏性压缩、机械兜底保证预算；LLM 摘要默认关闭、失败自动回退；用集成测试覆盖工具调用配对完整性。
- [LLM 摘要带来额外 token 成本与延迟] → 默认关闭，仅在配置阈值触发；摘要调用设超时并入机械兜底；离线测试用脚本化模型，不进入日常质量门禁。
- [会话持久化扩展点长期未实现导致后续改造成本] → `CheckpointBackend` 契约从 M3 起保持稳定（backend 注册 + `thread_id` 语义），持久化只需新增 backend 与恢复入口，不改 Agent 图/工具/UI。

## Migration Plan

Greenfield 项目，无数据或接口迁移。交付按 M0→M9 顺序推进，每个模块独立分支、通过人工 Review 后合并；任一模块可单独回滚。M9 完成后运行全量 E2E（离线 + 可选 live），随后归档 change 并把 9 个 capability 的 delta specs 同步进 `openspec/specs/`。

## Open Questions

- DeepSeek 示例配置的确切 `base_url`/`model`/密钥环境变量名由用户后续提供，仅影响示例配置、文档与 live 测试环境变量，不阻塞实现与任务拆分。
