# Tasks

## 1. M0 工程地基与配置

- [x] 1.1 创建 `pyproject.toml`、`uv.lock`（占位）、`src/` 布局、`.gitignore`、`scripts/bootstrap.sh` 与 `Makefile` 骨架；验证：在干净工作区执行 `make setup` 成功安装项目内 uv/Python 3.12/依赖，`uv run python -c "import minimum_coding_agent"` 通过
- [x] 1.2 实现 pydantic Settings 模型与分层加载（YAML > 默认值，环境变量与 CLI 覆盖），验证：配置优先级、未知字段、缺失必填项、密钥脱敏单测通过
- [x] 1.3 实现 CLI 骨架：默认入口（TUI 占位）、`run` 子命令占位、`--version`、`--help`、`--config/--workspace` 覆盖，验证：CLI 参数处理与退出码单测通过
- [x] 1.4 实现启动前校验（工作区存在且可写、模型端点配置完整）与可读错误输出，验证：非法工作区/缺失端点的启动失败单测通过
- [x] 1.5 配置 ruff（启用 `D` 规则并设为 Google convention）、pydoclint、pytest（默认排除 `live`）与 `make check`，验证：`make check` 全绿，且故意缺失 docstring 的样例能被检出并定位
- [x] 1.6 编写 `config/agent.example.yaml`（默认 DeepSeek 端点占位、无明文密钥）、`docs/conventions.md`（Google Style docstring/质量门禁/提交规范）、`AGENT.md` 骨架，验证：示例配置可被加载器解析，文档中的命令可执行
- [x] 1.7 输出 M0 评审包并暂停，等待人工 Review 确认；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## 2. M1 模型接入层

- [ ] 2.1 定义 `ChatModelProvider` 协议与 `ProviderRegistry`，验证：注册、重复注册、未知 provider 错误的单测通过
- [ ] 2.2 实现 OpenAI 兼容 provider（`base_url`/`api_key_env`/`model`/`temperature`/`max_tokens`/`timeout`）与配置映射，验证：配置到 `ChatOpenAI` 参数映射单测通过
- [ ] 2.3 实现 `ScriptedChatModel` 测试替身（流式片段 + `tool_calls`），验证：流式片段顺序、最终消息、工具调用脚本的单测通过
- [ ] 2.4 实现流式调用封装与错误分类（认证失败/超时/5xx/不可解析响应），验证：模拟异常的单测通过，错误文本不含密钥
- [ ] 2.5 添加 env-gated live smoke 测试（`pytest -m live`），验证：无 `MCA_LIVE_*` 时自动 skip；提供端点后可真实调用并断言收到流式输出
- [ ] 2.6 编写 provider 扩展文档与契约样例（含一个测试用 provider），验证：文档示例的注册方式在测试中可复用
- [ ] 2.7 输出 M1 评审包并暂停，等待人工 Review 确认；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## 3. M2 工具系统与基础工具

- [ ] 3.1 实现 `Toolset` 协议、`ToolContext`、工具 Registry 与统一结果协议（`{"ok": ...}`），验证：注册、重名拒绝、禁用工具集单测通过
- [ ] 3.2 实现 `WorkspaceGuard` 路径护栏，验证：`..` 逃逸、绝对路径逃逸、符号链接逃逸、工作区外写入的拒绝单测通过
- [ ] 3.3 实现 filesystem 工具集（`tree` 递归目录树、`glob_files`；排除目录、深度与条目上限），验证：目录树展开、深度限制、排除目录与结果截断的单测通过
- [ ] 3.4 实现 editor 工具集（`view` 文件/目录查看、`create`、`str_replace`、`insert`；1 起始行号、`end=-1` 到文件末尾、插入 0 表示开头），验证：范围读取、目录列表、创建冲突不覆盖、唯一替换、替换不唯一/不存在、插入越界均不修改文件的单测通过
- [ ] 3.5 实现 Bash 工具集（工作目录、超时终止、输出头尾截断、退出码、危险命令确认钩子、密钥环境变量剥离），验证：真实子进程单测（含 `sleep` 超时）通过
- [ ] 3.6 编写 `docs/tools.md`（工具清单、参数、错误语义、安全边界），验证：文档示例调用与工具实际输出一致
- [ ] 3.7 输出 M2 评审包并暂停，等待人工 Review 确认；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## 4. M3 Agent 核心

- [ ] 4.1 实现 `AgentState` 与 LangGraph `StateGraph`（agent/tools 节点、条件边、迭代计数与上限），验证：脚本化模型"工具调用→结果回注→最终回答"集成测试通过
- [ ] 4.2 实现系统提示装配（ROLE/ENVIRONMENT/TOOL_POLICY/PLANNING/RESPONSE_STYLE，及项目指令占位插入），验证：各节段存在、含工作区与模型信息、指令内容中的花括号不影响模板的单测通过
- [ ] 4.3 接入 `CheckpointBackend` 抽象与 `MemorySaver` 默认实现、多轮会话与 `thread_id` 隔离（预留持久化后端扩展点），验证：同会话引用前文、新会话清空、会话隔离与扩展点契约的集成测试通过
- [ ] 4.4 实现可组合上下文压缩管线（`ToolOutputTruncator`、可选 `LlmSummarizer`、`WindowDropper` 机械兜底），验证：机械兜底满足预算、脚本化模型 LLM 摘要、摘要失败回退、tool_call/ToolMessage 配对完整的测试通过
- [ ] 4.5 实现 `AgentEvent` 定义、运行时异步事件迭代器与取消语义，验证：事件顺序、工具事件含名称/结果摘要、错误与取消事件的集成测试通过
- [ ] 4.6 实现 headless `mca run` 文本渲染器（事件过程 + 最终结果 + 退出码），验证：脚本化模型下 CLI 集成测试通过；里程碑 A demo 可复现
- [ ] 4.7 编写 `docs/architecture.md`（分层、图结构、事件流、配置装配），验证：文档描述与实现的节点/事件类型一致
- [ ] 4.8 输出 M3 评审包并暂停，等待人工 Review 确认（里程碑 A：headless 完成一次编码任务）；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## 5. M4 规划与 TODO

- [ ] 5.1 实现 `TodoItem`、`AgentState.todos` 状态通道与 `write_todos` 工具（整体替换、id 唯一、状态枚举、长度校验、Command 更新状态），验证：合法更新、非法状态/重复 id 拒绝且原列表不变的测试通过
- [ ] 5.2 在运行时发布 `TodosUpdated` 事件并支持计划快照读取，验证：事件包含完整列表、跨轮保留、新会话清空的集成测试通过
- [ ] 5.3 扩充 PLANNING 提示节段（先计划、最多一个进行中、及时收尾、单步任务免计划），验证：prompt 内容断言与脚本化模型"先计划后执行"测试通过
- [ ] 5.4 headless 模式下展示计划变化并编写 `docs/planning.md`（TODO 语义与展示契约），验证：CLI 输出含计划变化，文档与实现一致
- [ ] 5.5 输出 M4 评审包并暂停，等待人工 Review 确认；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## 6. M5 Console UI

- [ ] 6.1 实现 Textual App 骨架、双栏布局、最小布局样式、状态栏，验证：`run_test` 启动应用并断言关键区域与状态栏文本通过
- [ ] 6.2 实现 ChatLog 与流式 Markdown 渲染（增量刷新、最终渲染、自动滚动），验证：`run_test` 流式增量与最终消息断言通过
- [ ] 6.3 实现工具调用卡片（开始/成功/失败、参数与结果摘要），验证：`run_test` 三种状态的卡片断言通过
- [ ] 6.4 实现 TODO 面板（实时刷新、空状态、不影响对话主区域），验证：`run_test` 空状态与更新断言通过
- [ ] 6.5 实现输入与运行控制（Enter 提交、Shift+Enter 换行、运行中忙碌与忽略提示、取消后恢复），验证：`run_test` 提交、取消、恢复输入断言通过
- [ ] 6.6 实现危险命令确认对话框并接入 Bash 确认钩子（headless 默认拒绝），验证：`run_test` 确认与拒绝两条路径断言通过
- [ ] 6.7 完成 composition root 的 TUI 装配，验证：`make run` 可启动交互界面，`make demo` 使用同一运行时正常输出
- [ ] 6.8 编写 `docs/ui.md`（界面结构、快捷键、取消与确认行为）并补充 UI 测试说明，验证：文档中的快捷键与行为与 `run_test` 断言一致
- [ ] 6.9 输出 M5 评审包并暂停，等待人工 Review 确认（里程碑 B：TUI 可用）；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## 7. M6 扩展机制

- [ ] 7.1 实现 `Command` 协议、命令 Registry 与 `/` 解析器（命令名、参数、未知命令提示），验证：注册、解析、未知命令、非法参数的单测通过
- [ ] 7.2 实现内置命令 `/help`、`/clear`、`/model`、`/todos`、`/quit`，验证：各命令行为的单元/`run_test` 测试通过
- [ ] 7.3 实现 `InstructionsLoader`（`AGENT.md` 读取、32KB 上限截断、新会话加载、注入系统提示），验证：加载/缺失/空文件/截断/注入 prompt 的测试通过
- [ ] 7.4 将命令与指令来源接入 composition root，编写 `docs/extensions.md`（新增命令与指令来源的步骤），验证：按文档注册一个新命令即可在控制台使用，核心模块无改动
- [ ] 7.5 输出 M6 评审包并暂停，等待人工 Review 确认；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## 8. M7 代码智能

- [ ] 8.1 实现 `search_text` 工具（关键词/正则、glob 过滤、默认排除目录、二进制跳过、结果与长度上限），验证：tmp 工作区检索、非法正则、超限截断、二进制跳过的单测通过
- [ ] 8.2 实现 `LanguageExtractor` 协议、`ExtractorRegistry` 与基于 tree-sitter 的 Python 提取器（outline/find_definition/find_references/语法错误容错），验证：fixture 代码的单测通过
- [ ] 8.3 实现 `tools/code.py` 的三个代码定位工具（路径护栏、结果截断、未支持语言提示），验证：工具集成测试通过
- [ ] 8.4 编写多语言扩展文档并加入测试用假提取器，验证：按文档注册新提取器后可用，Agent/UI 无改动
- [ ] 8.5 输出 M7 评审包并暂停，等待人工 Review 确认；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## 9. M8 MCP 集成

- [ ] 9.1 实现 MCP 配置模型与校验（stdio、必填字段、重名、不支持的 transport），验证：合法/非法配置单测通过
- [ ] 9.2 实现 `MCPToolLoader`（transport 注册表、stdio 传输、MultiServerMCPClient 薄封装、`mcp__<server>__<tool>` 命名空间、加载失败隔离、调用超时；预留流式 HTTP transport 扩展点），验证：stdio 替身服务器的加载、调用、参数错误、失败隔离集成测试通过
- [ ] 9.3 实现 MCP 生命周期（启动加载并收集 warning、退出关闭连接与子进程），验证：应用退出后无残留子进程、单服务器失败不影响启动的测试通过
- [ ] 9.4 编写 `docs/mcp.md` 与示例配置，验证：按文档配置替身服务器后可完成一次 MCP 工具调用
- [ ] 9.5 输出 M8 评审包并暂停，等待人工 Review 确认（里程碑 C：README 功能全覆盖）；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## 10. M9 整合与交付

- [ ] 10.1 实现离线端到端 demo（脚本化模型在临时工作区完成"读→改→跑测试"），验证：`make demo` 一键通过且断言文件修改与测试退出码
- [ ] 10.2 实现 live e2e 测试（真实端点修复 bug 并跑测试，env-gated），验证：无 `MCA_LIVE_*` 时 skip；提供端点与密钥后 `pytest -m live` 可真实运行
- [ ] 10.3 跨模块错误路径打磨（模型/工具/MCP/取消/超时/脱敏），验证：新增错误路径测试通过，手工 smoke 无崩溃
- [ ] 10.4 完善 README（安装、配置、TUI、headless、live 测试、开发规范、已知限制），验证：README 中的命令逐条可执行
- [ ] 10.5 全量回归：`make check` + `make demo` 全绿，9 个 spec 的验收场景均有对应测试覆盖
- [ ] 10.6 输出 M9 最终评审包并暂停，等待人工 Review 确认（里程碑 D：交付）；确认通过后，将评审结论与偏差写回 `design.md` D17、把新增工作补进 `tasks.md`，再勾选本任务

## Workflow follow-up

- 确认 10 个模块的 Review Gate 均已由用户确认通过，且 `design.md` D17 覆盖 M0–M9 的实现记录。
- 归档前检查每个模块的评审结论已写回产物（D17/tasks，必要时 specs/design），无仅存在于会话中的未落盘决定。
- 使用 `/openspec-archive-change` 归档本 change，并核对 `openspec/specs/` 下 9 个 capability 的主 spec 内容完整（Purpose 与全部 Requirement/Scenario）。
- 归档后复核 `make check` 仍通过，更新 README 中对项目状态的描述。
