# CLAUDE / Codex 项目说明

本仓库是 DoorAgent EDA 多 Agent 产品的完整工程骨架。若你是自动化代码 Agent，
请遵循以下硬约束：

1. 对外产品入口只有 `dooragent`（`dooragent run / resume / status / cancel`）。
2. 只允许存在四个 Agent 身份：`Master`、`A1`、`A2`、`A3`。Skill 不是子 Agent。
3. Agent 不直接读写其他 Agent 的 Workspace；跨 Agent 通信一律经过 Master
   与只读 Artifact 引用。
4. Master 不产生 EDA 业务证据；EDA 计算发生在 A1/A2/A3 的 Tool/Script 中。
5. 所有持久化路径必须是相对路径（相对 `product_run_root` 或 `workspace_root`）。
6. 未实现的 Tool 必须显式返回 `DECLARED_NOT_BOUND / TOOL_NOT_IMPLEMENTED
   / UNAVAILABLE`，不允许伪造成功、不允许生成假的 EDA 报告。
7. 模型 Provider/Key/URL 只允许从环境变量读取，不可硬编码进 Prompt、
   TOML、JSON、Workspace 或事件；密钥必须经过 `secret_redactor` 脱敏。
8. 所有跨进程消息使用 `write .partial → fsync → atomic rename`。
9. Schema 唯一权威来源是 `interfaces/`；运行时 Python 类型由此派生。
10. `scripts/*.py` 除 `scripts/a2/run.py` 与 `scripts/a3/synth_tool.py` 保留
    领域专属 CLI 外，其余统一支持 `--request-json / --result-json / --work-dir
    / --timeout-s`；退出码：`0=completed / 2=invalid request / 3=tool unavailable
    / 4=tool failed / 5=output invalid / 124=timeout / 130=cancelled`。

设计详细内容见 `DoorAgent-EDA-Multi-Agent-产品化方案.md`。
