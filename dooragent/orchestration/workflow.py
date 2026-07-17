"""WorkflowController：把 Master Facade 的高层调用组合到 orchestration 各能力。

- 依赖注入：state_store / gates / hooks / leases / sessions / exchange / bus / workspace
- 不承载 Agent 智能决策；纯确定性编排
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dooragent.events.bus import FileEventBus
from dooragent.events.envelope import build_event
from dooragent.orchestration.case_queue import CaseQueue, CaseKind
from dooragent.orchestration.exchange import ExchangeManager
from dooragent.orchestration.gates import GateController
from dooragent.orchestration.hooks import HookRegistry
from dooragent.orchestration.leases import LeaseScheduler
from dooragent.orchestration.recovery import Recoverer
from dooragent.orchestration.scheduler import Scheduler
from dooragent.orchestration.sessions import SessionRegistry
from dooragent.orchestration.state_store import StateEntry, StateStore
from dooragent.workspace.manager import WorkspaceManager


@dataclass(slots=True)
class WorkflowConfig:
    workflow_id: str
    initial_round_id: str = "r-1"
    budget: dict[str, Any] | None = None


class WorkflowController:
    """一个 Workflow 一实例；管理该 workflow 生命周期内的全部 orchestration 子系统。"""

    def __init__(
        self,
        *,
        product_run_root: Path,
        config: WorkflowConfig,
        pool_limits: dict[str, int] | None = None,
    ):
        self.product_run_root = Path(product_run_root).resolve()
        self.config = config
        self.workflow_root = self.product_run_root / "runs" / config.workflow_id
        self.workflow_root.mkdir(parents=True, exist_ok=True)
        (self.workflow_root / "workflow").mkdir(parents=True, exist_ok=True)

        self.workspace = WorkspaceManager(self.product_run_root)
        self.state = StateStore(self.workflow_root)
        self.gates = GateController(self.workflow_root)
        self.bus = FileEventBus(self.workflow_root)
        self.queue = CaseQueue(self.workflow_root)
        self.exchange = ExchangeManager(self.workflow_root)
        self.sessions = SessionRegistry()
        self.hooks = HookRegistry()
        limits = pool_limits or {"agent_instance": 4, "a1_instance": 2, "a3_evaluation": 2, "synthesis_job": 2}
        self.leases = LeaseScheduler(limits)
        self.scheduler = Scheduler(self.leases)
        self.recovery = Recoverer(self.workflow_root)

    # ------------------------------------------------------------------ #
    def bootstrap(self, request: dict[str, Any]) -> dict[str, Any]:
        """产品 CLI `run` 时的最小 bootstrap：登记 workflow、创建 Master Workspace。"""
        self.state.create(StateEntry(
            entity_type="workflow",
            entity_id=self.config.workflow_id,
            state_version=0,
            lifecycle_state="CREATED",
            health_state="normal",
        ))
        (self.workflow_root / "workflow" / "request.json").write_text(
            _json(request), encoding="utf-8",
        )
        master_ws = self.workspace.create_primary(
            workflow_id=self.config.workflow_id,
            workflow_round_id=self.config.initial_round_id,
            role="master",
        )
        # 首个事件：workflow.registered
        self.bus.publish(build_event(
            workflow_id=self.config.workflow_id,
            source="master",
            recipient="observer",
            kind="workflow.registered",
            workflow_round_id=self.config.initial_round_id,
            payload={"budget": self.config.budget or {}},
        ))
        self.state.transition(
            entity_type="workflow",
            entity_id=self.config.workflow_id,
            expected_state_version=0,
            expected_lifecycle_state="CREATED",
            patch={"lifecycle_state": "RTL_REGISTERED"},
            caused_by="workflow.registered",
        )
        return {
            "workflow_id": self.config.workflow_id,
            "workflow_round_id": self.config.initial_round_id,
            "master_workspace": master_ws.workspace_path,
        }

    def status(self) -> dict[str, Any]:
        wf = self.state.get("workflow", self.config.workflow_id)
        return {
            "workflow_id": self.config.workflow_id,
            "workflow_state": wf.to_dict() if wf else None,
            "leases": self.leases.snapshot(),
            "hooks": self.hooks.snapshot(),
            "cases_ready": len(self.queue.list_ready()),
            "events_ready": len(self.bus.list_ready()),
        }

    def cancel(self) -> dict[str, Any]:
        wf = self.state.get("workflow", self.config.workflow_id)
        if wf is None:
            return {"workflow_id": self.config.workflow_id, "status": "not_found"}
        self.state.transition(
            entity_type="workflow",
            entity_id=self.config.workflow_id,
            expected_state_version=wf.state_version,
            expected_lifecycle_state=wf.lifecycle_state,
            patch={"lifecycle_state": "CANCELLED"},
            caused_by="user.cancel",
        )
        return {"workflow_id": self.config.workflow_id, "status": "CANCELLED"}


def _json(data: Any) -> str:
    import json
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
