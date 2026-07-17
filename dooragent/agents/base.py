"""BaseAgent：Master / A1 / A2 / A3 共享的推理循环骨架。

- 每个 Agent 有 role / operations（operation → tool_ids 序列）
- 通过 ToolRegistry 调用 Tool；Tool 缺失时统一降级为 UNAVAILABLE
- 通过 ModelClient 做开放决策；模型未就绪时使用 rule-based policy
- Workspace / 相对路径由 WorkspaceManager 提供
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dooragent.agents.contracts import (
    AgentResult,
    AgentResultStatus,
    AgentTask,
    CapabilityState,
)
from dooragent.errors import DoorAgentError, ErrorCode
from dooragent.runtime.model_client import ModelClient
from dooragent.tooling import ToolRegistry
from dooragent.tooling.result import ToolStatus


@dataclass(slots=True)
class AgentContext:
    """一次 Task 执行的运行时上下文；只读传递给 Policy/Tool 调用。"""
    task: AgentTask
    agent_instance_id: str
    workspace_root: str
    product_run_root: Path
    model_client: ModelClient | None = None


class BaseAgent:
    role: str = "BASE"
    # operation → 顺序执行的 tool_id 列表（策略默认，可被 Policy 覆盖）
    operations: dict[str, list[str]] = {}

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        product_run_root: Path,
        instance_id: str | None = None,
        model_client: ModelClient | None = None,
    ):
        self.registry = registry
        self.product_run_root = product_run_root
        self.instance_id = instance_id or f"{self.role.lower()}-{uuid.uuid4().hex[:8]}"
        self.model_client = model_client

    # ------------------------------------------------------------------ #
    def execute(self, task: AgentTask) -> AgentResult:
        """同步执行一个 Task；跨进程/异步由 orchestration 层负责。"""
        if task.agent_role != self.role:
            return self._failed(task, ErrorCode.ROUTING_POLICY_VIOLATION,
                                f"task role {task.agent_role} routed to {self.role}")

        # health 短路
        if task.operation == "health":
            return AgentResult(
                task_id=task.task_id,
                agent_instance_id=self.instance_id,
                status=AgentResultStatus.COMPLETED,
                agent_role=self.role,
                metrics={"registered_tools": self.registry.list_ids()},
                capability_state=CapabilityState.HEALTHY,
            )

        tool_ids = self._select_tools(task)
        if not tool_ids:
            return self._failed(task, ErrorCode.INVALID_REQUEST,
                                f"unsupported operation: {task.operation}")

        ctx = AgentContext(
            task=task,
            agent_instance_id=self.instance_id,
            workspace_root=f"runs/{task.workflow_id}/workspaces/"
                           f"{task.workflow_round_id}/{self.role.lower()}-primary",
            product_run_root=self.product_run_root,
            model_client=self.model_client,
        )

        outputs: list[dict] = []
        diagnostics: list[dict] = []
        capability = CapabilityState.HEALTHY

        for tool_id in tool_ids:
            request = self._build_tool_request(ctx, tool_id)
            result = self.registry.invoke(request)
            outputs.extend([{"uri": r} for r in result.output_artifact_refs])
            if result.diagnostics:
                diagnostics.extend(result.diagnostics)
            if result.status in {ToolStatus.UNAVAILABLE, ToolStatus.UNSUPPORTED}:
                return AgentResult(
                    task_id=task.task_id,
                    agent_instance_id=self.instance_id,
                    agent_role=self.role,
                    status=AgentResultStatus.UNAVAILABLE,
                    output_artifact_refs=outputs,
                    diagnostics=diagnostics,
                    capability_state=CapabilityState.UNAVAILABLE,
                    error=result.error or {"code": result.error_code, "tool_id": tool_id},
                )
            if result.status != ToolStatus.COMPLETED:
                return AgentResult(
                    task_id=task.task_id,
                    agent_instance_id=self.instance_id,
                    agent_role=self.role,
                    status=AgentResultStatus.FAILED,
                    output_artifact_refs=outputs,
                    diagnostics=diagnostics,
                    capability_state=CapabilityState.DEGRADED,
                    error=result.error or {"code": result.error_code, "tool_id": tool_id},
                )
        return AgentResult(
            task_id=task.task_id,
            agent_instance_id=self.instance_id,
            agent_role=self.role,
            status=AgentResultStatus.COMPLETED,
            output_artifact_refs=outputs,
            diagnostics=diagnostics,
            capability_state=capability,
        )

    # ------------------------------------------------------------------ #
    # 可 override 的策略钩子
    # ------------------------------------------------------------------ #
    def _select_tools(self, task: AgentTask) -> list[str]:
        return self.operations.get(task.operation, [])

    def _build_tool_request(self, ctx: AgentContext, tool_id: str) -> dict[str, Any]:
        return {
            "tool_id": tool_id,
            "tool_interface_version": "1.0",
            "request_id": f"{ctx.task.task_id}--{tool_id}",
            "agent_instance_id": ctx.agent_instance_id,
            "workspace_root": ctx.workspace_root,
            "input_artifact_refs": [a.get("uri", str(a)) for a in ctx.task.input_artifact_refs],
            "parameters": ctx.task.constraints or {},
            "output_dir": f"artifacts/{self.role.lower()}/{ctx.task.task_id}/{tool_id}",
            "timeout_s": int(ctx.task.budget.get("timeout_s", 600)),
        }

    def _failed(self, task: AgentTask, code: ErrorCode, message: str) -> AgentResult:
        return AgentResult(
            task_id=task.task_id,
            agent_instance_id=self.instance_id,
            agent_role=self.role,
            status=AgentResultStatus.FAILED,
            capability_state=CapabilityState.DEGRADED,
            error={"code": code.value, "message": message},
        )
