# AGENT.md — minimum-coding-agent 项目指令

本文件是 AI Coding Agent 在本仓库工作的项目级约束。M0 阶段它是仓库内的工程约束摘要；M6 起会在新会话
开始时由 `InstructionsLoader` 读取，注入系统提示的 `PROJECT_INSTRUCTIONS` 节。完整规则见
`docs/conventions.md`，与 OpenSpec 产物冲突时以 `openspec/` 为准（工程约定的完整正文仍在
`docs/conventions.md`）。

## 开始工作前

1. 读 `openspec/changes/minimum-coding-agent-mvp/` 下的 `proposal.md`、`tasks.md`、`design.md`（相关
   Decision 与 D17 最近记录）及对应 capability 的 `specs/*/spec.md`；用 `openspec instructions apply`
   获取 change 上下文，不依赖历史聊天记录。
2. 用 `git status`、`git log --oneline -10` 确认当前分支与未提交改动；只实现 `tasks.md` 中当前模块的
   未完成项，不进入下一模块，不改后续模块的目录（`llm/`、`tools/`、`agent/`、`ui/` 等按模块顺序出现）。
3. 一个模块一条分支 `feat/mX-<topic>`，从最新 `master` 切出；不要直接改 `master`。
4. 提交信息用英文 Conventional Commits，scope 为模块号，例如 `feat(m0): add layered config loader`。

## 代码规范

- Python 标识符、注释、docstring、日志文本用英文；`README.md`、`docs/*.md`、OpenSpec 产物与 YAML 注释
  用中文；配置键、命令名、CLI 参数、环境变量用英文。
- 公开 API（模块、类、公开函数/方法、Protocol）使用 Google Style docstring：`Args:` / `Returns:` /
  `Raises:` / `Yields:` 按需书写并与签名一致；私有函数一行摘要；测试代码豁免。示例见
  `docs/conventions.md` 第 5 节。
- 每行不超过 100 字符；工具链优先 Python 3.12，代码保持 3.10 兼容基线，不使用 3.11+ 语法或标准库 API。
- 遵循 `design.md` D1 的分层与单向依赖：下层不得 import 入口层，禁止反向依赖。
- 不做投机抽象，优先可读、显式的 ReAct 循环实现（本项目用于学习，不使用隐藏循环的高阶封装）。
- 不把未实现的功能伪装成可用；当前模块的功能必须完整可用，尚未交付的能力要显式提示（如 M0 的 TUI /
  `mca run` 占位），未支持的场景返回明确错误而不是静默通过。

## 质量门禁

- `make check` 必须全绿（ruff 的 E/F/W/I/UP/B/D + Google pydocstyle convention、pydoclint、pytest），
  失败时不提交评审。
- 不要用全局 ignore 或删除测试来通过门禁；确需豁免时按 `pyproject.toml` 的 per-file-ignores 精确指定
  路径，并在评审包中说明原因。

## 测试

- 默认测试必须离线：脚本化模型（M1 起）、`tmp_path` 临时工作区、替身 MCP server（M8 起）；不调用真实
  模型端点，不依赖网络与本机全局状态。
- live 测试用 `@pytest.mark.live` 标记，默认被 `addopts` 排除，仅在显式启用时运行。
- 测试不依赖执行顺序与当前目录；优先断言事件序列和工作区副作用，而不是内部实现细节。
- 新增配置键、命令、工具、事件都要有测试；修 bug 先补回归测试。

## 配置与密钥

- 新增配置键必须同步更新 `src/minimum_coding_agent/config/settings.py`、`config/agent.example.yaml`
  与相关文档；配置是严格模式，未知键会启动失败。
- 优先 `provider.api_key_env`；不提交明文密钥、`.env`、`config/agent.yaml`；不打印或记录密钥；输出配置
  时使用 `Settings.redacted_dict()`。
- 命令与脚本一律走 `make` 或 `.tools/uv run ...`；不使用系统 pip、全局 uv 或工作区外缓存（bootstrap 在
  无法下载 uv 时会把系统 uv 复制到 `.tools/uv` 并告警，项目路径仍是唯一入口）。

## 文档与交付

- 代码行为变化同步更新文档与示例配置；文档中的命令必须可实际执行，不得描述尚未实现的能力（当前
  Makefile 只有 `setup`、`check`、`lint`、`test`、`run`）。
- 完成后运行 `make check`，输出评审包（改了什么/为什么、接口变化、运行方式、检查输出、限制与风险、
  建议 Review 重点），停下等待人工 Review；字段与模板见 `docs/conventions.md` 第 11 节。
- Review 通过后，先把结论与偏差写回 `design.md` D17 和 `tasks.md`（行为契约变化更新 `specs/`，方案变化
  更新对应 Decision），再合并分支并勾选 Review Gate；设计变更必须先改 OpenSpec 产物再改代码。

## 环境注意

- 首次使用或依赖变化后执行 `make setup`（项目内 uv、Python 与锁定依赖）。
- 网络受限时 bootstrap 可能回退系统 uv 或 Python 3.10；这属于已知环境差异，在评审包中记录实际版本，
  不要修改 `uv.lock` 或安装方式绕过。
- 工作区沙箱只允许写仓库内路径，保持 `.venv`、`.tools`、`.uv-cache`、`.uv-python` 本地化；不要手工删除
  这些目录，需要重建时重新运行 `make setup`。
