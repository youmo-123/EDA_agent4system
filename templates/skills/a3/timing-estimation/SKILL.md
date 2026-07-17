---
name: timing-estimation
role: A3
description: 使用 STA Backend 生成 arrival/Slack/critical path。
inputs: []
outputs: []
allowed_tools: []
evidence_requirements: []
gate2_conditions: []
stop_conditions: []
---

# A3 · timing-estimation

## 何时加载

使用 STA Backend 生成 arrival/Slack/critical path。

## 输入

- artifact refs：待补充
- constraints：待补充

## 输出

- 结构化 artifact：待补充

## 允许 Tool

只允许在 `configs/agents.toml` 中为本 Agent 列出的 Tool；具体 Tool ID
在本 Skill 的元信息 `allowed_tools` 中固化，`registry` 拒绝其它 Tool。

## 证据要求

- 输入 artifact 必须校验 hash / schema / producer / rtl_version_id
- 输出 artifact 必须绑定通用绑定字段（见项目方案 5.2 节）

## 常见陷阱

- 不允许伪造证据，缺失后端时必须返回 UNAVAILABLE
- 不允许把 Skill 提升为独立 Agent

## 失败恢复

出现依赖缺失、能力不可用或高风险偏离时，向 Master 发起 Gate 2 请求。
