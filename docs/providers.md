# 模型接入层（provider）使用与扩展

本文件说明 M1 交付的模型接入层：如何配置并选择模型提供商、如何以流式方式调用
OpenAI 兼容端点、失败如何分类呈现，以及如何新增一个 provider。行为契约见
`openspec/changes/minimum-coding-agent-mvp/specs/model-provider/spec.md`，实现取舍见
`design.md` D3。

## 1. 当前状态与边界（M1）

| 能力 | M1 现状 |
|---|---|
| provider 协议与注册表 | 已实现（`llm/base.py`、`llm/registry.py`） |
| 内置 provider | `openai-compatible`，基于 `langchain-openai` 的 `ChatOpenAI` |
| 流式调用封装 | 已实现（`llm/streaming.py`），供 M3 运行时消费 |
| 错误分类与脱敏 | 已实现（`llm/errors.py`），认证/超时/5xx/不可解析响应等 |
| 离线测试替身 | `ScriptedChatModel`（`llm/scripted.py`），M3 集成测试复用 |
| 启动期 provider 校验 | CLI 启动时校验 `provider.name` 已注册，未注册时退出码 4 并列出可用 provider |
| live smoke | `tests/live/`，需 `MCA_LIVE_*` 环境变量，默认跳过 |
| TUI / headless 运行时 | 仍为占位（M5 / M3）；M1 不发起任何真实模型调用 |

设计上只有 composition root（M3 的 `app.py`）与运行时知道“具体用哪个 provider”；CLI 在
M1 只做“名称已注册”的早期校验，JSON 配置到 `BaseChatModel` 的创建由
`create_chat_model()` 完成。

## 2. 分层与文件

```
src/minimum_coding_agent/llm/
├── base.py               # ChatModelProvider 协议（扩展契约）
├── registry.py           # ProviderRegistry：注册、重名拒绝、未知名称报错
├── openai_compatible.py  # 内置 provider：ProviderSettings -> ChatOpenAI
├── defaults.py           # create_default_registry() / create_chat_model()
├── scripted.py           # ScriptedChatModel：离线测试替身（不在生产路径使用）
├── streaming.py          # stream_chat() + TextDelta / MessageComplete 事件
└── errors.py             # 错误类型、分类与密钥脱敏
```

依赖方向遵守 `design.md` D1：`llm/` 依赖 `config/`，入口层（M3 起为 `app.py`）装配
`llm/`；`llm/` 不依赖 `agent/`、`tools/` 或 `ui/`。

## 3. 内置 provider 与配置映射

配置段 `provider`（定义在 `config/settings.py`，示例见 `config/agent.example.yaml`）：

| 配置键 | 映射到 `ChatOpenAI` | 说明 |
|---|---|---|
| `base_url` | `base_url` | OpenAI 兼容端点；DeepSeek 为 `https://api.deepseek.com` |
| `model` | `model` | 模型名，例如 `deepseek-chat` |
| `api_key_env` | `api_key`（运行时从该环境变量读取） | 推荐写法，配置文件不含明文密钥 |
| `api_key` | `api_key`（内联值） | 与 `api_key_env` 互斥；启动时会告警 |
| `temperature` | `temperature` | 0.0 ~ 2.0 |
| `max_tokens` | `max_tokens` | 单次响应最大 token 数 |
| `timeout_seconds` | `timeout` | 单次请求超时（秒） |
| —（固定值） | `max_retries=0` | 不在 SDK 内静默重试，由运行时决定是否重试，避免超时被成倍放大 |

密钥解析：配置里同时存在 `MCA_API_KEY` 时由加载器覆盖 `provider.api_key`（优先级见
`docs/conventions.md` 第 7 节）；provider 创建时通过 `ProviderSettings.resolved_api_key()`
解析，密钥以 `SecretStr` 保存在模型对象中，不打印、不记录。

代码用法：

```python
from minimum_coding_agent.config.loader import load_settings
from minimum_coding_agent.llm.defaults import create_chat_model

settings = load_settings()               # 需要 provider.base_url / model / API Key 齐备
model = create_chat_model(settings)      # 返回 langchain_core 的 BaseChatModel
```

M1 的 CLI 仍为占位实现，不会真的调用上面这段；M3 的运行时会在装配阶段使用同样的调用。

## 4. 流式调用契约

`stream_chat()` 接受任意可运行的聊天模型（包括 `bind_tools()` 之后的对象），逐片段产出
`TextDelta`，流结束后产出唯一一个携带完整 `AIMessage`（含 `tool_calls`）的
`MessageComplete`：

```python
from langchain_core.messages import HumanMessage

from minimum_coding_agent.llm.streaming import MessageComplete, TextDelta, stream_chat

async for event in stream_chat(model, [HumanMessage(content="hello")]):
    if isinstance(event, TextDelta):
        print(event.text, end="", flush=True)   # 增量片段，可立即渲染
    elif isinstance(event, MessageComplete):
        final_message = event.message           # 完整消息，可能包含 tool_calls
```

失败语义：

- 片段一旦产出就交给消费方，因此“流被中断”时已经显示的内容不会丢；
- 中断时抛出 `ModelCallError`，其 `partial_text` 保存已收到的文本，`category` 说明失败类型；
- 空流（一个片段都没有）按“不可解析响应”处理，抛 `ModelCallError`；
- `asyncio.CancelledError` 不会被包装，取消语义由上层负责。

## 5. 错误分类与脱敏

`classify_model_error()` 把 provider/LangChain 抛出的异常转换为用户可读错误：

| category | 触发场景 | retryable | hint 摘要 |
|---|---|---|---|
| `authentication` | 401 / 403，密钥或端点不正确 | 否 | 检查 `provider.api_key_env` 与 `provider.base_url` |
| `timeout` | `APITimeoutError`、`TimeoutError` | 是 | 重试或增大 `provider.timeout_seconds` |
| `network` | 连接失败、DNS/网络不可达 | 是 | 检查网络与端点地址 |
| `server` | 5xx 或 `InternalServerError` | 是 | 稍后重试或检查端点状态 |
| `rate_limit` | 429 | 是 | 稍后重试 |
| `invalid_request` | 400 / 404 / 422 等请求被拒绝 | 否 | 检查 `provider.model` 与参数 |
| `response` | 响应不可解析、空流、JSON/校验错误 | 是 | 确认端点是 OpenAI 兼容后重试 |
| `unknown` | 其他未预期异常 | 否 | 查看日志后重试 |

脱敏规则：

- 认证失败的原始 provider 细节不会进入错误文本（可能回显密钥）；
- 其他类别只保留最多 300 字符的摘要，并替换 `sk-...`、`Bearer ...`、`api_key=...`
  以及调用方显式传入的已知密钥；
- 错误对象只携带分类、可读摘要、修复提示与 `partial_text`，进程不会崩溃或卡死
  （是否重试由调用方决定）。

## 6. 扩展契约：新增一个 provider

扩展点只有两个要求（`llm/base.py` 的 `ChatModelProvider` 协议）：

1. `name`：非空字符串，必须与配置中的 `provider.name` 一致；
2. `create_model(settings, *, environ=None) -> BaseChatModel`：把 `ProviderSettings`
   转换成 LangChain 聊天模型；`environ` 用于解析 `api_key_env`，便于测试注入环境。

把实现注册进 `ProviderRegistry` 即可被配置选中，不需要修改 Agent 循环、工具系统或
控制台界面：

```python
from collections.abc import Mapping

from langchain_core.language_models import BaseChatModel

from minimum_coding_agent.config.settings import ProviderSettings
from minimum_coding_agent.llm.registry import ProviderRegistry
from minimum_coding_agent.llm.scripted import ScriptedChatModel, ScriptedTurn


class EchoProvider:
    """Provider contract sample that returns an offline scripted echo model."""

    name = "echo-scripted"

    def create_model(
        self,
        settings: ProviderSettings,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> BaseChatModel:
        reply = f"echo from {settings.model or 'unnamed model'}"
        return ScriptedChatModel(
            turns=(ScriptedTurn(chunks=(reply,)),),
            repeat_last=True,
        )


registry = ProviderRegistry()
registry.register(EchoProvider())   # 注册后，provider.name="echo-scripted" 即可选中
```

以上样例的**权威副本**在 `tests/fixtures/providers.py`（文档与测试共用同一份代码），
契约测试见 `tests/unit/test_provider_contract.py`，覆盖：

- 按文档方式注册后，`create_chat_model()` 能按配置选中该 provider 并完成流式调用；
- 同一 provider 可被多次调用（多轮场景的前置能力）；
- 未注册的 `provider.name` 报错并列出可用 provider 名称；
- 不满足契约的对象（缺少 `name`、`name` 为空/非字符串、缺少或不可调用的
  `create_model`）在**注册阶段**报 `ProviderContractError`，不会拖到运行期。

真实 provider（例如未来的 Anthropic）只需新增一个模块并在 composition root 注册，
配置选择、错误分类与流式封装都可复用。

## 7. 测试

离线（默认 `make check` 会执行，不访问网络）：

| 测试文件 | 覆盖 |
|---|---|
| `tests/unit/test_provider_registry.py` | 注册、重名拒绝、未知 provider、契约违规 |
| `tests/unit/test_openai_provider.py` | 配置到 `ChatOpenAI` 的参数映射、缺失配置、密钥解析 |
| `tests/unit/test_scripted_model.py` | 流式片段顺序、最终消息、`tool_calls` 脚本、脚本耗尽 |
| `tests/unit/test_streaming.py` | 片段顺序、最终消息、中断保留已收内容、空流 |
| `tests/unit/test_errors.py` | 认证/超时/5xx/不可解析响应分类与脱敏 |
| `tests/unit/test_provider_contract.py` | 文档契约样例可复用、未知 provider |

live smoke（可选，默认被 `addopts = -m 'not live'` 排除）：

```bash
export MCA_LIVE_BASE_URL="https://api.deepseek.com"
export MCA_LIVE_API_KEY="<真实密钥>"
export MCA_LIVE_MODEL="deepseek-chat"
make test-live
```

- 三个变量任一缺失时，live 测试自动 skip；提供后断言真实端点返回流式输出，并验证
  `tool_calls`（端点需支持 OpenAI function calling，DeepSeek 等主流端点支持）；
- **终端可见性**：`make test-live` 以 `-s` 运行，live 测试会把模型流式响应实时打印到终端，便于目视确认；
  直接运行 `.tools/uv run pytest -m live` 时 pytest 默认捕获输出（仅失败时显示），可自行加 `-s`；
- **事件循环约束**：`langchain-openai 1.7.2` 在进程内用 `lru_cache` 缓存默认 `httpx.AsyncClient`，
  该 client 不能跨事件循环复用；`tests/live/` 的测试因此用
  `@pytest.mark.asyncio(loop_scope="session")` 共享一个 session 级事件循环。新增 live 测试时沿用该写法
  （或共用同一 model/client），否则第二个测试会报 `RuntimeError: Event loop is closed`；
- live 测试不进入日常质量门禁，也不要在 CI 中保存真实密钥。

## 8. 模块 demo（离线）

```bash
make demo-llm     # 等价于 .tools/uv run python scripts/demo_llm.py
```

输出依次展示：注册的 provider 列表、配置到 `ChatOpenAI` 的映射（不发起请求）、
`ScriptedChatModel` 经 `stream_chat()` 的流式片段与 `tool_calls` 最终消息、以及
错误分类 + 密钥脱敏。整个过程离线，不需要 API Key。

## 9. 与后续模块的关系与已知限制

- M3 运行时用 `create_chat_model()` 取模型、`model.bind_tools(...)` 绑定工具后交给
  `stream_chat()`；`MessageComplete` 中的 `tool_calls` 驱动 ReAct 循环；
- M5 控制台只消费 M3 的事件流，不直接依赖 provider；
- M1 不实现 Anthropic 适配器，只保留上面的扩展契约；不实现工具调用能力协商差异，
  端点必须支持 OpenAI Chat Completions 与 function calling；
- `ScriptedChatModel` 仅用于测试与 demo，生产装配不会注册它；
- `max_retries=0` 是刻意选择：让超时与错误按配置时间暴露，重试策略留给运行时/用户。
