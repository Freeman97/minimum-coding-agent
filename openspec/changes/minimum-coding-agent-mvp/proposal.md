# Proposal

## Why

当前仓库只有 [README.md](../../../README.md) 描述的目标与架构，尚无任何实现。需要从零构建一个**学习目的、最小可用、ReAct 风格的单 Agent Coding Agent**，技术栈按 README 要求使用 LangChain + LangGraph + Textual/Rich，功能覆盖多轮会话、代码生成与编辑、可配置 LLM 接入、文档搜寻、规划与 TODO、代码定位、MCP 集成、`/` 命令扩展与 `AGENT.md` 自定义指令。

之所以以"一次总体设计 + 分模块实现"的方式推进：功能横跨模型接入、工具执行、Agent 循环、TUI 与扩展机制，模块间依赖强；按模块拆分并在每个模块完成后暂停做人工 Review，既能保证学习路径清晰，也能把设计偏差控制在单个模块内。

## What Changes

- 新建 Python 项目（`uv` 管理 Python 3.12 + `pyproject.toml` + 锁文件，`src/` 布局），实现单 Agent 的 ReAct Coding Agent。
- **配置与启动**：YAML + 环境变量配置；CLI 双入口——默认启动 Textual TUI，`mca run "<task>"` 提供 headless 模式（用于测试、评审与 CI）。
- **模型接入**：`ChatModelProvider` 工厂接入 OpenAI 兼容端点（自定义 `base_url`/`api_key`/`model`），支持流式；为 Anthropic 等其他格式预留 Provider 扩展点，MVP 不实现。
- **工具系统**：统一的 Toolset/Registry 与安全边界（工作区路径护栏、Bash 超时/输出截断/危险命令确认钩子）；内置文件系统、文本编辑、Bash、TODO、文档检索、代码定位工具集。
- **Agent 核心**：显式 LangGraph `StateGraph`（`agent <-> tools`）实现 ReAct 循环；系统提示词模板；`MemorySaver` 支撑多轮会话；统一 `AgentEvent` 事件流供 TUI/headless 消费。
- **规划与 TODO**：`todos` 状态通道 + `write_todos` 工具 + 提示词约束，TUI 可实时展示。
- **Console UI**：Textual App / Theme / Components，覆盖流式 Markdown 对话、工具调用卡片、输入框、状态栏、TODO 面板。
- **扩展机制**：`/` 命令注册与内置命令集；`AGENT.md` 自定义指令注入；MCP 服务器配置、工具加载与命名空间。
- **工程质量**：pytest 单测/集成测试 + env-gated 真实模型 live 测试；ruff（启用 `D` 规则、Google docstring convention）+ pydoclint 作为模块级门禁；每个模块交付评审包。
- **BREAKING**：无（greenfield 项目）。

## Capabilities

### New Capabilities

- `project-foundation`: 应用启动、YAML/env 配置加载与校验、CLI 入口（TUI 与 headless）、日志与错误呈现、工程测试与质量门禁基础。
- `model-provider`: 可配置 LLM 接入点：Provider 注册/工厂、OpenAI 兼容实现、流式输出、连接与调用错误处理，以及新增 Provider 的扩展契约。
- `tool-system`: 工具注册/执行框架与内置文件系统、文本编辑、Bash 工具集；工作区路径约束、命令超时/输出截断、工具错误向模型回传的语义。
- `agent-runtime`: 单 Agent ReAct 循环、系统提示装配（角色/环境/工具策略/指令）、多轮会话状态、迭代上限与统一 `AgentEvent` 事件流。
- `task-planning`: 规划与 TODO 列表：todo 状态模型、`write_todos` 工具、规划/执行/收尾的提示约束。
- `console-ui`: Textual 控制台界面：对话流与流式 Markdown 渲染、工具调用卡片、输入与快捷键、状态栏、TODO 面板、主题。
- `extensions`: `/` 命令扩展机制（注册、解析、内置 `/help`、`/clear`、`/model`、`/todos`、`/quit`）与 `AGENT.md` 自定义指令加载/注入。
- `code-intelligence`: 工作区内文档与代码的文本检索、Python 代码定位（文件大纲、定义查找、标识符引用），并预留多语言 AST 扩展架构。
- `mcp-integration`: MCP 服务器配置与加载（stdio）、MCP 工具到 LangChain 工具的转换、命名空间隔离、失败隔离与生命周期管理。

### Modified Capabilities

- 无（仓库当前没有既有 specs）。

## Impact

- **新增代码**：`src/minimum_coding_agent/`（`config/`、`llm/`、`tools/`、`agent/`、`extensions/`、`ui/`、`cli.py`）、`tests/`、`config/agent.example.yaml`、`AGENT.md`、`docs/conventions.md`、`pyproject.toml`、`Makefile`（或等价质量脚本）。
- **新增依赖**：`langchain`、`langgraph`、`langchain-openai`、`textual`、`rich`、`pydantic`、`pyyaml`、`python-dotenv`、`mcp`、`langchain-mcp-adapters`、`tree-sitter` + `tree-sitter-language-pack`（M7 引入）、`pytest`、`ruff`、`pydoclint`。
- **工具链**：`uv` 安装、缓存与 Python 解释器均放在项目目录内，不改动系统 Python；通过锁文件保证可复现。
- **流程**：OpenSpec `config.yaml` 增加项目上下文/规则与 apply 门禁指引；每个模块在独立分支实现，人工 Review 通过后合并，全部完成后归档本 change 并同步主 specs。
- **明确不做（out of scope）**：联网检索/网页抓取（未来作为独立工具集）、多 Agent、Web UI、会话持久化（先 `MemorySaver`，SQLite checkpointer 留扩展点）、LSP/类型级语义引用解析、Anthropic 等非 OpenAI 格式的原生实现、多语言代码定位实现（仅预留架构）。
