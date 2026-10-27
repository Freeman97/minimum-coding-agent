# 工程规范（minimum-coding-agent）

本文件是仓库级工程约定的正文，面向人类开发者与 AI Coding Agent。`openspec/config.yaml` 只记录
Agent 无法从代码推断的项目上下文，`AGENT.md` 是项目指令的简短版本，更细的工程规则以本文件为准。

## 当前状态（M1）

当前处于 M1（模型接入层）。下表中的"已存在"指本分支 `feat/m1-model-provider` 的真实能力：

| 能力 | M1 现状 |
|---|---|
| CLI `mca` | 参数解析、启动校验与 provider 名称校验；无子命令时打印 TUI 占位提示后退出；`mca run "<task>"` 为 headless 占位（M3 实现） |
| 配置 | pydantic v2 Settings、分层加载、严格校验、启动前校验、密钥脱敏 |
| 模型接入 | provider 协议/注册表、`openai-compatible` provider、流式封装、错误分类与脱敏、`ScriptedChatModel`、live smoke（见 `docs/providers.md`） |
| 质量门禁 | `make check` = ruff + pydoclint + pytest（离线，默认排除 live） |
| 工具系统 / TUI / 命令扩展 / AGENT.md 注入 / MCP | 分别由 M2 / M5 / M6 / M6 / M8 实现，M1 尚无这些能力 |

因此：文档、示例配置与测试中不要宣称上表中"未实现"的能力已经可用；命令示例只使用当前真实存在的
`make setup|check|lint|test|test-live|run|demo-llm` 与已实现的 `mca` 参数。`make test-live` 需要
`MCA_LIVE_*` 环境变量，`make demo-llm` 是 M1 的离线 demo；`make demo` 在 M3 才加入。

## 1. 语言与命名

- Python 代码：标识符、注释、docstring、日志与错误文本使用英文；模型可见的工具描述也使用英文（M2 起）。
- 文档与配置注释：`README.md`、`docs/*.md`、OpenSpec 产物以及 YAML 注释使用中文。
- 配置键、命令名、CLI 参数、环境变量、分支名与 commit message 使用英文。
- 命名遵循 Python 生态惯例：模块/函数/变量 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE_CASE`；
  测试文件 `test_*.py`，测试函数 `test_<被测行为>`。

## 2. 仓库布局

当前目录（标注"规划"的目录在对应模块交付时才出现），完整设计见 `design.md` 的 D1 / D2：

```
minimum-coding-agent/
├── Makefile / pyproject.toml / uv.lock / uv.toml / .gitignore
├── README.md
├── AGENT.md                        # 项目指令；M6 起由 InstructionsLoader 注入系统提示
├── config/agent.example.yaml       # 示例配置；复制为 config/agent.yaml（后者已被 gitignore）
├── docs/conventions.md             # 本文件
├── scripts/bootstrap.sh            # 在仓库内安装 uv / Python / 依赖
├── src/minimum_coding_agent/
│   ├── __init__.py / __main__.py
│   ├── cli.py                      # M0：参数解析、启动校验、入口占位
│   ├── config/                     # M0：settings / loader / validation
│   ├── app.py                      # 规划：composition root（M3 起接入）
│   ├── llm/                        # M1：provider 协议/注册表/流式封装/错误分类/脚本化模型
│   ├── tools/                      # 规划：M2 工具系统（M7 增加代码工具）
│   ├── agent/                      # 规划：M3 运行时 / 事件 / 上下文压缩
│   ├── codeintel/                  # 规划：M7 代码智能
│   ├── extensions/                 # 规划：M6 命令与 AGENT.md、M8 MCP
│   └── ui/                         # 规划：M5 Textual 控制台
└── tests/                          # M0 起 unit/；M1 加 live/、fixtures/；integration/ui 随对应模块加入
```

依赖方向由 `design.md` D1 规定：入口层（`cli.py`、`ui/`）只依赖运行时与配置；`agent/` 依赖
`llm/`、`tools/`、`codeintel/`；`tools/` 与 `extensions/` 不依赖 UI；任何模块都不 import 入口层。
新增模块时先确认依赖方向，禁止反向依赖。模型接入层的使用与扩展契约见 `docs/providers.md`。

## 3. 工具链（工作区本地化）

开发沙箱只允许写工作区，且环境中可能没有系统 pip / uv / ripgrep，所以工具链必须落在仓库目录内：

| 位置 | 用途 |
|---|---|
| `.tools/uv` | 项目内 uv 可执行文件（固定 0.13.1，由 `make setup` 安装） |
| `.uv-python/` | uv 下载的 CPython 解释器（优先 3.12） |
| `.venv/` | 项目虚拟环境（由 uv 管理，不要手工 `python -m venv`） |
| `.uv-cache/` | uv 缓存（`uv.toml` 的 `cache-dir` 已固定到项目内） |

- **解释器**：优先 CPython 3.12；`make setup` 在无法下载 3.12 时回退系统 3.10（`requires-python >= 3.10`）。
  Python 3.10 是兼容基线：不要使用 3.11+ 才有的语法或标准库 API，`ruff` 的 `target-version = "py310"`
  会做静态检查。
- **命令入口**：日常操作统一走 `make`；Makefile 会导出 `UV_CACHE_DIR`、`UV_PYTHON_INSTALL_DIR`、
  `UV_PROJECT_ENVIRONMENT`，保证不写到工作区之外。需要直接调用 uv 时使用项目内 `.tools/uv run ...`；
  在仓库根目录直接运行 `uv run ...` 也可用（`uv.toml` 已把 cache 固定到 `.uv-cache/`），但它会使用 PATH 中
  的 uv 而不仅是项目内固定版本，因此日常仍以 make 目标为准。不要使用系统 pip 或工作区外缓存。
- **不要使用**系统 pip、全局 uv、外部 venv；不要手工编辑 `.venv/`。
- **锁定**：运行期依赖写在 `pyproject.toml` 的 `dependencies`，开发工具写在 `dependency-groups.dev`；
  更新后用 `uv sync` 重新生成并提交 `uv.lock`。
- **按模块增量添加依赖**：M0 只保留基础依赖；M1 已加 `langchain-openai`（含 `langchain-core`）与开发依赖
  `pytest-asyncio`；M7 加 `tree-sitter` 系列，M8 加 `mcp` / `langchain-mcp-adapters`。不要提前引入后续模块的依赖。
- `.venv/`、`.tools/`、`.uv-cache/`、`.uv-python/`、`config/agent.yaml`、`.env` 均已 gitignore，禁止提交。

## 4. make 命令

`make` 不带目标时执行 `help`（默认目标）。当前可用目标：

| 命令 | 实际执行 | 作用 |
|---|---|---|
| `make` / `make help` | 打印目标列表 | 默认目标，查看可用命令 |
| `make setup` | `bash scripts/bootstrap.sh` | 安装项目内 uv、Python 解释器与锁定依赖，并验证 `import minimum_coding_agent` |
| `make lint` | `.tools/uv run ruff check src tests`；`.tools/uv run pydoclint --config pyproject.toml src` | 静态检查 + Google Style docstring 校验 |
| `make test` | `.tools/uv run pytest` | 离线测试（`addopts = -m 'not live'` 自动排除 live） |
| `make test-live` | `.tools/uv run pytest -m live` | live 模型 smoke；需 `MCA_LIVE_*` 变量，缺失时自动 skip |
| `make check` | `lint` + `test` | 质量门禁，提交与评审前必须全绿 |
| `make run` | `.tools/uv run mca` | 启动交互控制台；M5 前只打印占位提示并退出 |
| `make demo-llm` | `.tools/uv run python scripts/demo_llm.py` | M1 模型接入层离线 demo（不访问网络） |

- `make lint` 的 ruff 范围是 `src tests`（`scripts/` 等不参与），pydoclint 只检查 `src`。
- `make run` 前必须有可用的 provider 配置与 API Key（例如 `MCA_CONFIG=config/agent.yaml DEEPSEEK_API_KEY=... make run`）；
  否则启动校验失败：底层 `mca` 进程以 exit code 4 退出，`make` 自身则以 2 退出（目标失败）。以 `mca` 的退出码
  判断失败原因，这是预期行为。
- `make check` 是每个模块的 Definition of Done 的第一条；失败时修代码，不要靠删测试或全局关闭规则来规避。
- `make test-live` 只在显式提供 `MCA_LIVE_BASE_URL` / `MCA_LIVE_API_KEY` / `MCA_LIVE_MODEL` 后执行真实
  调用；不要把密钥写进脚本、测试或 CI，也不要把它并入日常门禁。
- `make demo-llm` 是 M1 的离线评审 demo：展示配置映射、脚本化流式输出与错误脱敏，不需要 API Key。
- 首次使用、依赖变化或 `uv.lock` 更新后重新执行 `make setup`；bootstrap 是幂等的，失败会重试依赖同步。
- 不要在 `make setup` 运行期间并行执行 `make check` 等目标（会争用同一个 `.venv`）。

## 5. Docstring 规范（Google Style）

公开 API 必须写 docstring，这是硬性规范，由 ruff `D` 规则与 pydoclint 机械检查：

- 范围：公开模块、公开类、公开函数、公开方法、Protocol 成员；私有函数写一行摘要即可；`tests/**` 与
  `scripts/**` 通过 per-file-ignores 豁免 ruff `D` 规则（但测试仍需可读）。
- 结构：首行摘要（祈使句、以句号结尾，且能独立说明行为），空一行后写详细说明；按需使用
  `Args:` / `Returns:` / `Raises:` / `Yields:` / `Attributes:` 节。
- `Args:` 覆盖所有参数（含 keyword-only 参数），参数名与签名一致；没有返回值的函数不写 `Returns:`；
  显式 `raise` 的异常必须写 `Raises:`，不要写不会发生的异常。
- 行宽上限 100 字符（ruff `line-length`）；docstring 中的标识符用双反引号包起来，例如 ``path``。
- 类的构造参数写在 `__init__` docstring 的 `Args:` 中；pydoclint 已开启 `allow-init-docstring`，类 docstring
  与 `__init__` docstring 可以共存（异常类见 `config/loader.py` 与 `config/validation.py` 的实际写法）。
- 公开函数即使只有一行摘要也必须补全 `Args:` / `Returns:`（`skip-checking-short-docstrings = false`）；
  私有函数写一行摘要即可（`skip-checking-private-functions = true`）。
- ruff 的 `D` 规则与 pydoclint 互补：前者检查摘要格式、首行标点、公开性等，后者检查 `Args:` /
  `Returns:` / `Raises:` 与函数签名的一致性，两者都必须通过。

**正确示例**（参数、返回值、异常都齐全）：

```python
def resolve_workspace_path(
    workspace: Path, relative: str, *, must_exist: bool = False
) -> Path:
    """Resolve a workspace-relative path and reject escapes.

    Args:
        workspace: Absolute workspace root directory.
        relative: Path supplied by the model; it must stay inside ``workspace``.
        must_exist: Whether the target must already exist on disk.

    Returns:
        The resolved absolute path.

    Raises:
        ValueError: If the path resolves outside ``workspace``.
    """
```

**错误示例**（公开函数只有摘要，缺少 `Args:` 与 `Returns:`）：

```python
def count_lines(path: Path) -> int:
    """Count lines in a text file."""
    return len(path.read_text(encoding="utf-8").splitlines())
```

上例 ruff 的摘要格式检查可以通过，但 pydoclint 会报 DOC101（缺少参数说明）与 DOC201（缺少返回值说明）
——这正是"ruff + pydoclint 双门禁"的意义。公开函数连摘要都没有时，ruff 会报 D103。该行为由
`tests/unit/test_quality_gate.py` 锁定：如果门禁配置被放宽，测试会失败。

## 6. 质量门禁

质量门禁的配置事实来源是 `pyproject.toml`，当前内容如下：

- **ruff**：`select = ["E", "F", "W", "I", "UP", "B", "D"]`，`pydocstyle.convention = "google"`，
  `line-length = 100`，`target-version = "py310"`；排除 `.venv`、`.tools`、`.uv-cache`、`.uv-python`；
  `tests/**` 与 `scripts/**` 豁免 `D` 规则。
- **pydoclint**：`style = "google"`，检查 Google Style docstring 的 `Args/Returns/Raises` 一致性；关键选项为
  `arg-type-hints-in-docstring = false`（类型由签名标注承载）、`check-return-types = false`、
  `allow-init-docstring = true`、`skip-checking-short-docstrings = false`（公开函数一行摘要也要补全）、
  `skip-checking-private-functions = true`（私有函数只写摘要）。pydoclint 默认会读取当前目录 `pyproject.toml`
  的 `[tool.pydoclint]`；Makefile 仍显式传 `--config pyproject.toml`，保证从任意目录调用时使用同一份配置。
- **pytest**：`minversion = 8.0`、`testpaths = ["tests"]`、`addopts = "-m 'not live'"`；`live` marker
  在 `pyproject.toml` 中注册，代表"调用真实模型端点"的测试，默认不执行。M1 起启用 pytest-asyncio
  （`asyncio_mode = "strict"`，异步测试显式加 `@pytest.mark.asyncio`）。
- 不新增全局忽略规则；确需局部豁免时在 `pyproject.toml` 的 per-file-ignores 中精确指定路径，并在评审包
  里说明原因。

## 7. 配置规范

配置模型在 `src/minimum_coding_agent/config/settings.py`（pydantic v2，`extra="forbid"`，
未知键直接报错），加载逻辑在 `config/loader.py`，启动校验在 `config/validation.py`。

**加载优先级（从高到低）：命令行参数 > 环境变量 > YAML 文件 > 内置默认值。**

- 命令行：`--config PATH` 选择配置文件（覆盖 `MCA_CONFIG`），`--workspace DIR` 覆盖工作区。
- 环境变量只有以下五个，且是显式映射，不支持按嵌套字段泛化覆盖：

  | 环境变量 | 作用 |
  |---|---|
  | `MCA_CONFIG` | 配置文件路径（`--config` 优先级更高） |
  | `MCA_WORKSPACE` | 工作区路径（`--workspace` 优先级更高） |
  | `MCA_BASE_URL` | 覆盖 `provider.base_url` |
  | `MCA_API_KEY` | 覆盖 `provider.api_key`（内联语义，见下方注意事项） |
  | `MCA_MODEL` | 覆盖 `provider.model` |

- 环境变量映射为 `provider.api_key`（内联字段）。若配置文件使用 `provider.api_key_env`，同时又设置了
  `MCA_API_KEY`，按优先级由 `MCA_API_KEY` 覆盖并移除文件中的 `api_key_env` 引用（环境变量优先），
  不会报互斥错误。同一个配置文件里同时写 `api_key` 与 `api_key_env` 仍然互斥（exit code 3）。
- 相对 `workspace` 相对启动时的当前目录解析，加载后会被规范化为绝对路径；启动校验要求该目录存在、
  是目录且可写（否则 exit code 4）。
- 严格模式：出现未定义的键、类型错误或越界取值时启动失败，错误信息包含文件路径、字段路径与原因
  （exit code 3），且不打印敏感值。空的或纯空白的 `provider.api_key` / `base_url` / `model` /
  `api_key_env` / `instructions_file` 视为非法配置（exit code 3）；`api_key_env` 指向的环境变量为空或纯空白
  时视为未配置 API Key（启动校验 exit code 4）。
- **只读取这五个 `MCA_*` 变量**：裸 `BASE_URL` / `MODEL` / `API_KEY` / `WORKSPACE` / `CONFIG` 等环境变量
  一律忽略，避免 CI 或 shell 中的同名变量意外改变配置；`load_settings(environ=...)` 的注入完全隔离于进程
  环境变量，测试因此可以在任意环境下复现。
- 示例配置为 `config/agent.example.yaml`；使用时复制为 `config/agent.yaml`（已被 gitignore），
  通过 `--config` 或 `MCA_CONFIG` 指定，不要直接修改示例文件来填写真实密钥。
- **新增配置键**必须同时更新 `src/minimum_coding_agent/config/settings.py` 的 pydantic 模型、
  `config/agent.example.yaml` 与
  相关文档，并在当前模块的测试中覆盖默认值、合法值与非法值；否则示例配置会因未知键而启动失败。

`provider` 与后续模块的关系：M1 已实现 provider 层与启动期 provider 名称校验（未注册名称以退出码 4
终止并列出可用名称）；TUI/headless 运行时仍为占位，`agent`、`tools`、`mcp` 等配置段分别由 M3、
M2/M7、M8 消费。示例文件中出现这些键是 schema 要求，不代表对应能力已实现；provider 的配置映射与
扩展契约见 `docs/providers.md`。

## 8. 密钥与敏感信息

- 优先使用 `provider.api_key_env` 指向环境变量（示例为 `DEEPSEEK_API_KEY`），配置文件与仓库中不出现明文密钥。
- 允许 `provider.api_key` 内联写法，但与 `api_key_env` 互斥；使用内联密钥（配置文件 `api_key` 或环境变量
  `MCA_API_KEY`）时启动会打印告警：
  `provider.api_key is set inline; prefer provider.api_key_env ...`。该告警不是错误，但应在本地排查后消除。
- 密钥在模型层用 `pydantic.SecretStr` 保存，报错信息通过 `hide_input_in_errors=True` 隐藏输入；
  需要打印配置时调用 `Settings.redacted_dict()`，其中 `provider.api_key` 固定显示为 `***REDACTED***`，
  `mcp.servers[*].env` 的所有值也会被遮蔽（这些值常用于传递 MCP 连接密钥）。
- 禁止把密钥写入日志、异常、事件、测试快照、commit message 或 README；禁止 `echo $DEEPSEEK_API_KEY`
  之类的调试命令留在脚本或文档中。
- `.env`、`config/agent.yaml` 已被 gitignore；提交前用 `git status` / `git diff` 自查是否误带本地配置。
- live 测试通过 `MCA_LIVE_BASE_URL` / `MCA_LIVE_API_KEY` / `MCA_LIVE_MODEL` 注入端点与密钥，默认不执行，
  也不要把密钥写进测试代码或 CI 配置。

## 9. CLI 与退出码

`mca` 入口在 `src/minimum_coding_agent/cli.py`，参数面如下：

- 无子命令：启动交互式控制台；M0 为占位实现，打印提示与配置摘要后以 0 退出（M5 接入 Textual）。
- `mca run "<task>"`：headless 执行单次任务；M0 为占位实现（M3 接入运行时）。
- `mca --version` / `mca --help`：输出版本或帮助后退出，不启动控制台（argparse 行为）。
- `--config PATH` / `--workspace DIR`：可放在子命令前后；`--workspace` 会覆盖配置中的工作区。

退出码是稳定契约，后续模块必须沿用：

| 退出码 | 含义 | 触发场景 |
|---|---|---|
| `0` | 成功 | 正常退出；`--help` / `--version` 也算成功 |
| `2` | 用法错误 | argparse 解析失败（未知参数、缺少 `run` 的任务参数等） |
| `3` | 配置错误 | 配置文件不存在/不是文件/非法 YAML/不符合 schema（含未知键、越界值） |
| `4` | 启动校验失败 | 工作区不存在/不是目录/不可写；`base_url`、`model` 或 API Key 缺失；`provider.name` 未注册 |

错误与告警输出到 stderr（前缀 `error:` / `warning:`），正常结果输出到 stdout。M1 的 `run`/无子命令占位
实现返回 `0` 或配置/启动错误码 `3` / `4`（含未注册的 `provider.name`，stderr 会列出可用 provider）；
headless 运行时失败、迭代上限等运行期退出码在 M3 定义，并与代码、测试一起补进本表。

## 10. 分支、提交与合并

- 分支命名：`feat/mX-<topic>`，一个模块一条分支（当前 M1 为 `feat/m1-model-provider`，M0 已合并）；从最新的 `master`
  切出，Review 通过后合回 `master`。
- 提交信息：英文 Conventional Commits，格式 `<type>(<module>): <subject>`，scope 用模块号。
  - 示例：`feat(m0): add layered configuration loader`、`test(m0): cover CLI exit codes`、
    `docs(m0): document docstring and quality rules`、`fix(m2): reject symlink escapes in workspace guard`。
  - 常用 type：`feat`、`fix`、`test`、`docs`、`refactor`、`chore`、`build`、`ci`、`perf`。
  - subject 用英文、祈使句、小写开头、不加句号；正文解释"为什么"，不要只重复 diff。
- 提交要聚焦：一个提交完成一件可描述的事，不把无关格式化混进功能提交；不提交生成物（见第 3 节）。
- 不直接向 `master` 提交；合并前确保 `make check` 全绿且 Review Gate 已确认。

## 11. 模块交付流程与 Review Gate

项目按 `tasks.md` 的 M0–M9 顺序逐模块交付，**每个模块独立会话/分支，通过人工 Review 后才进入下一模块**
（`design.md` D16）。标准流程：

1. **会话启动**：执行 `openspec instructions apply` 获取 change 的 proposal/specs/design/tasks 上下文；
   先读当前模块的 tasks 段、相关 Decision、`design.md` D17 最近记录，以及 `git status` / `git log`。
   不要依赖上一个会话的聊天记录。
2. **一次性只做一个模块**：从最新 `master` 建 `feat/mX-<topic>` 分支；明确声明"不进入下一模块"，不修改
   后续模块的目录与文件。
3. **实现 + 测试 + 文档**：按本规范写代码与 docstring；测试离线；同步更新模块相关文档与示例配置。
4. **自测**：`make check` 全绿；有 demo 的模块运行模块 demo（M0 用 `config/agent.example.yaml` 走一次
   CLI 路径验证配置可加载）。
5. **输出评审包并暂停**，固定字段：
   - 改了什么、为什么；
   - 对外接口或行为变化（配置键、退出码、事件、工具语义等）；
   - 如何运行 demo；
   - 测试与质量命令输出摘要；
   - 已知限制与风险；
   - 建议 Review 的重点。
6. **Review 通过后写回产物**（顺序不能反）：先把结论与偏差追加到 `design.md` D17，把新增工作补进
   `tasks.md`，行为契约变化更新 `specs/`，方案变化更新对应 Decision；然后合并 `master` 并勾选该模块的
   Review Gate 任务。评审未通过则在本分支继续迭代，重跑门禁后再提交。
7. **Definition of Done（每模块）**：`make check` 全绿；模块 demo 可运行；公开 API docstring 合规；
   无未解决的设计偏差；评审包已提交；评审结论已写回产物。

D17 记录模板（每模块一条，不超过 10 行，只写"为什么/取舍/偏差"）：

```markdown
#### Mx <模块名>

- 分支/提交：`feat/mx-*`，`<sha>`..`<sha>`
- 交付范围：...
- 与设计的偏差及原因：...（无则写"无"）
- 评审中定下的取舍：...
- 对后续模块的影响/前置条件：...
- 遗留问题/已知限制：...
```

规则：可执行项落到 `tasks.md`；行为契约变化改 `specs/`；方案变化改 `design.md` 对应 Decision；测试日志与
完整 diff 留在评审包和 commit，不写入 D17。**设计或契约变更必须先改 OpenSpec 产物再改代码**，禁止代码
领先文档；`openspec update` 只刷新生成的指令文件，不用于修订产物内容（修订用 `/openspec-update-change`
或直接编辑后 `openspec validate`）。

## 12. 测试策略

| 层级 | 方式 | 覆盖范围 |
|---|---|---|
| 单元 | pytest + `tmp_path` | 配置加载/优先级/校验、CLI 参数与退出码、路径护栏、各工具、命令注册、AGENT.md、搜索与定位、MCP 配置校验 |
| Agent 集成 | `ScriptedChatModel`（M1 起） | ReAct 循环、工具结果回注、迭代上限、多轮会话、上下文压缩、事件序列、待办列表状态 |
| UI | Textual `run_test`（M5 起） | 提交、流式渲染、工具卡片、待办列表面板、取消、错误呈现 |
| MCP | stdio 替身服务器（M8 起） | 加载、命名空间、调用、失败隔离、退出清理 |
| live（可选） | `pytest -m live` | M1 端点 smoke、M9 真实编码任务 E2E；无环境变量时自动 skip |

- **默认测试必须离线**：不访问真实模型端点、不依赖网络、不依赖本机全局状态；外部交互用脚本化模型、
  `tmp_path` 临时工作区与替身 MCP server。M1 起异步测试用 pytest-asyncio（strict 模式，显式
  `@pytest.mark.asyncio`）。
- live 测试用 `@pytest.mark.live` 标记，`pyproject.toml` 的 `addopts` 默认排除；M1 起 live 测试位于
  `tests/live/`，用 `make test-live` 按需运行，且必须先设置 `MCA_LIVE_BASE_URL` / `MCA_LIVE_API_KEY` /
  `MCA_LIVE_MODEL`，缺失变量时自动 skip。
- live 测试模块共享一个 session 级事件循环（`@pytest.mark.asyncio(loop_scope="session")`）：
  `langchain-openai` 在进程内缓存默认 `httpx.AsyncClient`，跨事件循环复用会报
  `RuntimeError: Event loop is closed`；新增真实端点测试沿用该写法。
- 测试独立可重复：不依赖执行顺序、不共享可变全局状态、不依赖当前工作目录；需要文件系统时一律用 `tmp_path`
  或 `tmp_path_factory`。
- 命名与结构：M0 只有 `tests/unit/`；M1 增加 `tests/live/` 与 `tests/fixtures/`（可复用测试替身，
  通过 `tests/conftest.py` 加入 `sys.path`）；`tests/integration/`、`tests/ui/` 随 M3/M5 加入。
  文件 `test_*.py`，函数 `test_<行为>`，断言说明失败时的可理解原因。
- 关键断言优先验证**事件序列与工作区副作用**（文件内容、退出码、输出文本），而不是内部实现细节。
- M0 的测试必须覆盖：配置优先级、未知字段拒绝、密钥脱敏、CLI 参数与退出码 0/2/3/4、启动校验失败路径，
  以及"缺失 docstring 的样例能被质量门禁检出"。

## 13. 已知环境问题与排障

- **`make` 可能未安装**：Makefile 依赖 GNU make。若环境缺少 make（本沙箱曾出现），先用包管理器安装
  （Ubuntu/Debian：`sudo apt-get install -y make`），不要绕过 Makefile 手工拼命令；团队内可用用户级安装
  （无需 root）以免影响系统目录。
- **网络受限**：`scripts/bootstrap.sh` 优先从 astral.sh 下载固定版本 uv；若该域名或 github 不可达，会
  回退到系统已安装的 uv（版本可能高于 0.13.1）；再失败则报错退出。依赖仍由 `uv.lock` 锁定，回退不影响
  可复现性，但要在评审包中记录实际 uv / Python 版本。
- **Python 3.12 下载失败**：bootstrap 会依次尝试 3.12、3.11、3.10、3；当前仓库的 `.venv` 基于
  CPython 3.12，若回退到系统 Python 3.10，功能不受影响（`requires-python >= 3.10`），但不要使用
  3.11+ 语法。
- **pypi 不可达**：`uv sync` 会失败，bootstrap 最多重试 3 次；依赖安装失败不是代码问题，不要修改锁文件或
  改用系统 pip 绕过，应报告环境限制。
- **沙箱只允许写工作区**：不要设置指向仓库外的 `UV_CACHE_DIR` / `UV_PYTHON_INSTALL_DIR`；`uv.toml` 已把
  cache 固定到 `.uv-cache/`。工具链目录一律不要手工删除，需要清理时用 `make setup` 重建。
- **无系统 pip / ripgrep**：不要假设它们在 PATH 中；Python 依赖通过项目 `.venv` 与 uv 获取，搜索能力由
  M7 的纯 Python 实现提供。
- **docstring 报 DOC101 / DOC201**：公开函数缺少 `Args:` 或 `Returns:` 说明，按第 5 节补全；一行摘要不会
  被豁免。**DOC301** 只在关闭 `allow-init-docstring` 时出现；本项目已开启该选项，构造参数写在
  `__init__` docstring 的 `Args:` 中即可，不要为此关闭检查。
- **未知 provider 启动失败**：stderr 出现 `unknown model provider '<name>'; available providers: ...`
  表示 `provider.name` 未注册；改成内置的 `openai-compatible`，或按 `docs/providers.md` 的扩展契约注册
  新 provider。
- **配置加载失败**：先用 `--config` 显式指定文件并检查 stderr 的 `configuration is invalid (<path>)` 与
  `- <field>: <reason>` 行；未知键通常是拼写错误或用了后续模块才出现的键。密钥相关失败检查
  `provider.api_key_env` 指向的变量是否已导出。
