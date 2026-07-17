"""OrchestrationRuntime：把 WorkflowController 按 workflow_id 缓存并暴露到 CLI。

- 支持多个并发 workflow（不同 workflow_id）
- 单进程实例；生产可扩展为多进程共享同一文件系统 root
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode
from dooragent.orchestration.workflow import WorkflowController, WorkflowConfig


class OrchestrationRuntime:
    def __init__(self, product_run_root: Path):
        self.root = Path(product_run_root).resolve()
        self._controllers: dict[str, WorkflowController] = {}

    def get(self, workflow_id: str) -> WorkflowController:
        if workflow_id not in self._controllers:
            wf_root = self.root / "runs" / workflow_id
            if not wf_root.exists():
                raise DoorAgentError(
                    ErrorCode.INVALID_REQUEST,
                    f"workflow not initialized: {workflow_id}",
                )
            self._controllers[workflow_id] = WorkflowController(
                product_run_root=self.root,
                config=WorkflowConfig(workflow_id=workflow_id),
            )
        return self._controllers[workflow_id]

    def create(self, workflow_id: str, request: dict[str, Any],
               *, budget: dict[str, Any] | None = None,
               initial_round_id: str = "r-1") -> WorkflowController:
        if workflow_id in self._controllers:
            raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"workflow already exists: {workflow_id}")
        controller = WorkflowController(
            product_run_root=self.root,
            config=WorkflowConfig(
                workflow_id=workflow_id,
                initial_round_id=initial_round_id,
                budget=budget,
            ),
        )
        self._controllers[workflow_id] = controller
        controller.bootstrap(request)
        return controller

    def list(self) -> list[str]:
        return sorted(self._controllers.keys())
