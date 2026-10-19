# Spec Delta

## Purpose

定义在不修改核心 Agent 的情况下扩展交互命令与项目指令的机制：`/` 命令的注册与解析、内置命令行为、`AGENT.md` 自定义指令加载与注入。

## ADDED Requirements

### Requirement: 命令注册与解析

系统 SHALL 支持以 `/` 开头的交互命令；命令注册信息包含名称、说明与处理器；未知命令 SHALL 返回可用命令提示。

#### Scenario: 执行已注册命令

- **WHEN** 用户输入已注册命令
- **THEN** 执行对应处理器，且该输入不会作为普通消息发送给模型

#### Scenario: 未知命令

- **WHEN** 用户输入未注册的命令
- **THEN** 提示命令未知并列出当前可用命令

#### Scenario: 带参数命令

- **WHEN** 用户输入带参数的命令
- **THEN** 参数按该命令声明的约定解析；参数不合法时给出用法说明

### Requirement: 内置命令集

系统 SHALL 内置 `/help`、`/clear`、`/model`、`/todos`、`/quit`，分别用于展示帮助、开启新会话、展示当前模型信息、展示当前计划与退出应用。

#### Scenario: 帮助

- **WHEN** 用户执行 `/help`
- **THEN** 列出全部可用命令及其说明

#### Scenario: 清空会话

- **WHEN** 用户执行 `/clear`
- **THEN** 会话历史与 TODO 清空，界面回到新会话状态

#### Scenario: 查看模型

- **WHEN** 用户执行 `/model`
- **THEN** 显示当前提供商与模型名称，不要求切换模型

#### Scenario: 查看计划

- **WHEN** 用户执行 `/todos`
- **THEN** 显示当前 TODO 列表及状态

#### Scenario: 退出应用

- **WHEN** 用户执行 `/quit`
- **THEN** 应用正常退出并释放外部连接

### Requirement: AGENT.md 自定义指令

系统 SHALL 在工作区根目录读取 `AGENT.md`，并在新会话开始时将其内容注入系统提示；文件缺失、为空或超过大小上限时 SHALL 有明确且安全的处理。

#### Scenario: 加载自定义指令

- **WHEN** 工作区存在合法的 `AGENT.md`
- **THEN** 新会话的系统提示包含其内容，且内容不覆盖系统安全约束

#### Scenario: 文件缺失或为空

- **WHEN** 工作区不存在 `AGENT.md` 或文件为空
- **THEN** 运行正常，不注入空内容

#### Scenario: 文件超过上限

- **WHEN** `AGENT.md` 超过配置的大小上限
- **THEN** 截断后注入，并向用户提示截断行为

### Requirement: 扩展稳定性

新增命令或自定义指令来源 SHALL 不要求修改 Agent 循环、工具系统或控制台核心代码。

#### Scenario: 新增命令

- **WHEN** 开发者注册一个新命令
- **THEN** 无需修改核心模块即可在控制台中使用该命令

#### Scenario: 新增指令来源

- **WHEN** 增加一个自定义指令来源
- **THEN** 通过既有装配点接入，Agent 循环与控制台核心不改动
