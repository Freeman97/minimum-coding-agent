# Spec Delta

## Purpose

定义应用从启动到可交互的基础行为：配置的加载与校验、CLI 双入口、以及开发与自动化所依赖的工程质量门禁。

## ADDED Requirements

### Requirement: 分层配置加载

系统 SHALL 从配置文件、环境变量与命令行参数分层加载配置，优先级为命令行 > 环境变量 > 配置文件 > 内置默认值，并在启动前完成类型与必填校验。

#### Scenario: 使用默认配置启动

- **WHEN** 未提供配置文件且未设置覆盖项
- **THEN** 系统使用内置默认值启动；若缺少必填项则终止启动并给出可执行的修复提示

#### Scenario: 环境变量覆盖配置文件

- **WHEN** 配置文件与环境变量同时设置同一模型参数
- **THEN** 环境变量的值生效

#### Scenario: 非法配置被拒绝

- **WHEN** 配置文件包含未知字段、非法类型或越界取值
- **THEN** 启动终止，错误信息指出文件、字段与原因，且不打印敏感值

### Requirement: CLI 双入口

系统 SHALL 提供两个入口：无子命令时启动交互式控制台；`run` 子命令以 headless 方式执行单次任务并输出过程与结果。

#### Scenario: 启动交互式控制台

- **WHEN** 用户运行 `mca`
- **THEN** 系统启动交互式控制台

#### Scenario: headless 执行单次任务

- **WHEN** 用户运行 `mca run "<task>"`
- **THEN** 系统在指定工作区执行任务，将运行事件以文本输出，任务成功时以退出码 0 结束

#### Scenario: headless 执行失败

- **WHEN** 任务执行出错或未在迭代上限内完成
- **THEN** 进程以非 0 退出码结束，并输出失败原因

#### Scenario: 版本与帮助

- **WHEN** 用户运行 `mca --version` 或 `mca --help`
- **THEN** 输出项目版本或可用入口说明，且不启动控制台

### Requirement: 启动前工作区与端点校验

系统 SHALL 在启动前校验工作区目录存在且可写、模型端点配置完整；校验失败时 SHALL 在进入交互界面之前终止并给出修复建议。

#### Scenario: 工作区不存在

- **WHEN** 配置的工作区路径不存在或不可写
- **THEN** 启动终止并提示该路径与权限问题

#### Scenario: 模型端点配置不完整

- **WHEN** 未配置模型端点或缺少 API Key
- **THEN** 启动终止并指出缺失的配置项及其配置位置

### Requirement: 统一质量门禁

项目 SHALL 提供统一的质量命令，执行静态检查、Google 风格 docstring 校验与自动化测试；任一检查失败时命令 SHALL 以非 0 退出。

#### Scenario: 全部检查通过

- **WHEN** 运行质量命令且静态检查、docstring 校验与测试均通过
- **THEN** 命令以 0 退出并输出各检查摘要

#### Scenario: docstring 不合规

- **WHEN** 公开 API 缺少符合 Google 风格要求的 docstring
- **THEN** 质量命令失败并定位到文件与行号

#### Scenario: 测试失败

- **WHEN** 任一自动化测试失败
- **THEN** 质量命令以非 0 退出并展示失败用例摘要
