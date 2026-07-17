"""Gate 1（新轮次）与 Gate 2（轮内长线程）控制器。

Gate 1 状态机（方案 7.1）：
  REQUESTED → VALIDATING → CREATING_WORKSPACES → SPAWNING → OPEN
  失败：REJECTED | WORKSPACE_FAILED | SPAWN_FAILED | ROLLED_BACK

Gate 2 状态机（方案 7.2）：
  OPENED → WAITING_SAFEPOINT
        → WAITING_MASTER | WAITING_SUB_INFO | WAITING_DEPENDENCY | WAITING_A1
        → RESOLVING → RESOLVED | ABORTED | EXPIRED
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode


# ---------------------------------------------------------------------------- #
class Gate1State(StrEnum):
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    CREATING_WORKSPACES = "CREATING_WORKSPACES"
    SPAWNING = "SPAWNING"
    OPEN = "OPEN"
    REJECTED = "REJECTED"
    WORKSPACE_FAILED = "WORKSPACE_FAILED"
    SPAWN_FAILED = "SPAWN_FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class Gate2State(StrEnum):
    OPENED = "OPENED"
    WAITING_SAFEPOINT = "WAITING_SAFEPOINT"
    WAITING_MASTER = "WAITING_MASTER"
    WAITING_SUB_INFO = "WAITING_SUB_INFO"
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    WAITING_A1 = "WAITING_A1"
    RESOLVING = "RESOLVING"
    RESOLVED = "RESOLVED"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"


class Resolution(StrEnum):
    CONTINUE = "CONTINUE"
    CONTINUE_WITH_CONSTRAINTS = "CONTINUE_WITH_CONSTRAINTS"
    REDIRECT = "REDIRECT"
    ROLLBACK = "ROLLBACK"
    STOP_ROUND = "STOP_ROUND"
    REJECT_REQUEST = "REJECT_REQUEST"


@dataclass(slots=True)
class Gate1Result:
    gate1_id: str
    workflow_id: str
    workflow_round_id: str
    role: str
    state: Gate1State
    reason: str = ""
    workspace_path: str | None = None
    created_at: float = 0.0


@dataclass(slots=True)
class Gate2Thread:
    gate2_thread_id: str
    workflow_id: str
    workflow_round_id: str
    originator_role: str
    originator_instance_id: str
    reason: str
    state: Gate2State
    created_at: float
    resolution: Resolution | None = None
    resolution_id: str | None = None
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    must_produce: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------- #
class GateController:
    """
    workflow/gates/
      gate1/<gate1_id>.json
      gate2/<gate2_thread_id>/state.json
      gate2/<gate2_thread_id>/<seq>-resolution/master-resolution.json
    """

    def __init__(self, workflow_root: Path):
        self.root = Path(workflow_root).resolve() / "workflow" / "gates"
        (self.root / "gate1").mkdir(parents=True, exist_ok=True)
        (self.root / "gate2").mkdir(parents=True, exist_ok=True)

    # ---- Gate 1 ---- #
    def open_gate1(self, *, workflow_id: str, workflow_round_id: str, role: str,
                   workspace_path: str | None = None) -> Gate1Result:
        g1 = Gate1Result(
            gate1_id=f"g1-{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            workflow_round_id=workflow_round_id,
            role=role,
            state=Gate1State.OPEN,
            workspace_path=workspace_path,
            created_at=time.time(),
        )
        _atomic_write(self.root / "gate1" / f"{g1.gate1_id}.json", {
            "gate1_id": g1.gate1_id,
            "workflow_id": g1.workflow_id,
            "workflow_round_id": g1.workflow_round_id,
            "role": g1.role,
            "state": g1.state.value,
            "reason": g1.reason,
            "workspace_path": g1.workspace_path,
            "created_at": g1.created_at,
        })
        return g1

    def fail_gate1(self, gate1_id: str, *, state: Gate1State, reason: str) -> None:
        target = self.root / "gate1" / f"{gate1_id}.json"
        if not target.exists():
            raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"gate1 not found: {gate1_id}")
        data = json.loads(target.read_text(encoding="utf-8"))
        data["state"] = state.value
        data["reason"] = reason
        _atomic_write(target, data)

    # ---- Gate 2 ---- #
    def open_gate2(self, *, workflow_id: str, workflow_round_id: str,
                   originator_role: str, originator_instance_id: str,
                   reason: str) -> Gate2Thread:
        thread = Gate2Thread(
            gate2_thread_id=f"g2-{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            workflow_round_id=workflow_round_id,
            originator_role=originator_role,
            originator_instance_id=originator_instance_id,
            reason=reason,
            state=Gate2State.OPENED,
            created_at=time.time(),
        )
        thread_dir = self.root / "gate2" / thread.gate2_thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(thread_dir / "state.json", _gate2_to_dict(thread))
        return thread

    def resolve(self, thread_id: str, *, resolution: Resolution,
                allowed_actions: list[str] | None = None,
                forbidden_actions: list[str] | None = None,
                must_produce: list[str] | None = None,
                evidence: dict[str, Any] | None = None) -> Gate2Thread:
        thread_dir = self.root / "gate2" / thread_id
        state_path = thread_dir / "state.json"
        if not state_path.exists():
            raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"gate2 thread not found: {thread_id}")
        data = json.loads(state_path.read_text(encoding="utf-8"))
        thread = _gate2_from_dict(data)
        thread.state = Gate2State.RESOLVED
        thread.resolution = resolution
        thread.resolution_id = f"res-{uuid.uuid4().hex[:12]}"
        thread.allowed_actions = list(allowed_actions or [])
        thread.forbidden_actions = list(forbidden_actions or [])
        thread.must_produce = list(must_produce or [])
        _atomic_write(state_path, _gate2_to_dict(thread))
        # 生成 resolution 目录
        existing = sorted(thread_dir.glob("*-resolution"))
        seq = len(existing) + 1
        res_dir = thread_dir / f"{seq:03d}-resolution"
        res_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(res_dir / "master-resolution.json", {
            "gate2_thread_id": thread_id,
            "resolution_id": thread.resolution_id,
            "resolution": resolution.value,
            "allowed_actions": thread.allowed_actions,
            "forbidden_actions": thread.forbidden_actions,
            "must_produce": thread.must_produce,
            "evidence": evidence or {},
            "created_at": time.time(),
        })
        return thread

    def get_gate2(self, thread_id: str) -> Gate2Thread | None:
        state_path = self.root / "gate2" / thread_id / "state.json"
        if not state_path.exists():
            return None
        return _gate2_from_dict(json.loads(state_path.read_text(encoding="utf-8")))

    def ack(self, thread_id: str, *, resolution_id: str, status: str,
            planned_next_action: str = "", will_produce: list[str] | None = None) -> Path:
        thread_dir = self.root / "gate2" / thread_id
        if not thread_dir.exists():
            raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"gate2 thread not found: {thread_id}")
        # 找到对应的 resolution 目录
        for res_dir in sorted(thread_dir.glob("*-resolution")):
            master_res = json.loads((res_dir / "master-resolution.json").read_text(encoding="utf-8"))
            if master_res.get("resolution_id") == resolution_id:
                ack_path = res_dir / "feedback-ack.json"
                _atomic_write(ack_path, {
                    "status": status,
                    "resolution_id": resolution_id,
                    "planned_next_action": planned_next_action,
                    "will_produce": will_produce or [],
                })
                return ack_path
        raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"resolution_id not found: {resolution_id}")


def _gate2_to_dict(t: Gate2Thread) -> dict[str, Any]:
    return {
        "gate2_thread_id": t.gate2_thread_id,
        "workflow_id": t.workflow_id,
        "workflow_round_id": t.workflow_round_id,
        "originator_role": t.originator_role,
        "originator_instance_id": t.originator_instance_id,
        "reason": t.reason,
        "state": t.state.value,
        "resolution": t.resolution.value if t.resolution else None,
        "resolution_id": t.resolution_id,
        "allowed_actions": t.allowed_actions,
        "forbidden_actions": t.forbidden_actions,
        "must_produce": t.must_produce,
        "created_at": t.created_at,
    }


def _gate2_from_dict(d: dict[str, Any]) -> Gate2Thread:
    return Gate2Thread(
        gate2_thread_id=d["gate2_thread_id"],
        workflow_id=d["workflow_id"],
        workflow_round_id=d["workflow_round_id"],
        originator_role=d["originator_role"],
        originator_instance_id=d["originator_instance_id"],
        reason=d["reason"],
        state=Gate2State(d["state"]),
        resolution=Resolution(d["resolution"]) if d.get("resolution") else None,
        resolution_id=d.get("resolution_id"),
        allowed_actions=list(d.get("allowed_actions", [])),
        forbidden_actions=list(d.get("forbidden_actions", [])),
        must_produce=list(d.get("must_produce", [])),
        created_at=float(d.get("created_at", 0.0)),
    )


def _atomic_write(target: Path, data: Any) -> None:
    import os
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".partial")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    try:
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
    except OSError:  # pragma: no cover
        pass
    os.replace(tmp, target)


# ---------------------------------------------------------------------------- #
# Manifest 中 master_resolve_gate 的 builtin entrypoint 引用点
# ---------------------------------------------------------------------------- #
def resolve_gate(request: dict[str, Any], *, controller: GateController | None = None) -> dict[str, Any]:
    """把 request 中的 gate2_thread_id + resolution 应用到 GateController。

    仅在单进程内使用；实际运行时由 WorkflowController 注入 controller。
    """
    if controller is None:
        return {"state": "UNAVAILABLE", "reason": "controller not injected"}
    thread = controller.resolve(
        request["gate2_thread_id"],
        resolution=Resolution(request["resolution"]),
        allowed_actions=request.get("allowed_actions"),
        forbidden_actions=request.get("forbidden_actions"),
        must_produce=request.get("must_produce"),
        evidence=request.get("evidence"),
    )
    return {
        "gate2_thread_id": thread.gate2_thread_id,
        "resolution": thread.resolution.value if thread.resolution else None,
        "resolution_id": thread.resolution_id,
        "state": thread.state.value,
    }
