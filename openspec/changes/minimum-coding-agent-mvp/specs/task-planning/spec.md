# Spec Delta

## Purpose

定义 Agent 的规划与 TODO 行为，使多步骤任务具有显式计划，并让用户可以在运行过程中观察计划进展。

## ADDED Requirements

### Requirement: TODO 状态模型

系统 SHALL 在会话状态中维护 TODO 列表，每项包含唯一标识、内容与状态（待办、进行中、已完成）；TODO 状态 SHALL 在同一会话的多轮之间保留。

#### Scenario: 计划跨轮保留

- **WHEN** 某一轮运行写入了 TODO 列表
- **THEN** 同一会话的后续轮次可读取到相同的列表与状态

#### Scenario: 新会话清空

- **WHEN** 开启新会话
- **THEN** TODO 列表为空

### Requirement: TODO 更新工具

系统 SHALL 提供工具用于整体写入或更新 TODO 列表；非法输入（未知状态、重复标识、超长内容）SHALL 被拒绝并以结构化错误返回模型。

#### Scenario: 写入合法列表

- **WHEN** 模型写入合法的 TODO 列表
- **THEN** 会话状态中的列表被更新，并发布 TODO 更新事件

#### Scenario: 未知状态值

- **WHEN** 模型提交了未定义的状态值
- **THEN** 返回结构化错误，且原列表保持不变

#### Scenario: 重复标识

- **WHEN** 模型提交了重复的 TODO 标识
- **THEN** 返回结构化错误，且原列表保持不变

### Requirement: 规划提示约束

系统提示 SHALL 要求 Agent 在多步骤任务开始前先建立计划、同一时刻最多保留一个进行中项、随进展更新计划并在结束时收尾；对简单单步问题 SHALL 允许直接回答而不创建计划。

#### Scenario: 多步骤任务

- **WHEN** 用户请求需要多步操作的任务
- **THEN** 系统提示包含先规划、控制进行中数量与及时更新计划的要求

#### Scenario: 单步问题

- **WHEN** 用户提出简单的单步问题
- **THEN** 系统提示允许直接回答，不强制创建 TODO

#### Scenario: 任务收尾

- **WHEN** 任务进入收尾
- **THEN** 系统提示要求将已完成项标记完成或清理残留计划

### Requirement: 计划可见性

TODO 的每次变更 SHALL 通过统一事件流发布完整列表，使控制台可实时展示、headless 可输出计划变化。

#### Scenario: 发布计划变更

- **WHEN** TODO 列表发生变更
- **THEN** 发布包含完整列表与各项状态的更新事件

#### Scenario: 控制台实时展示

- **WHEN** 控制台正在运行任务
- **THEN** TODO 面板随更新事件实时刷新
