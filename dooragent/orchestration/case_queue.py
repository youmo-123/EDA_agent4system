"""Master Case Queue：Master 需要处理的待办事项（跨事件、跨 Gate、跨轮次）。

- 每个 Case 是一个原子文件；write .partial → fsync → atomic rename
- 支持 claim/mark-done/mark-failed
- Case 与 Event 相似但有 correlation_id 和 priority；用于 Master 主循环
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode


class CaseKind(StrEnum):
    OPEN_GATE1 = "open_gate1"
    RESOLVE_GATE2 = "resolve_gate2"
    ROUTE_TASK = "route_task"
    REVIEW_EVIDENCE = "review_evidence"
    ARCHIVE_ROUND = "archive_round"
    PUBLISH_OUTPUTS = "publish_outputs"
    HOOK_ESCALATION = "hook_escalation"


@dataclass(slots=True)
class Case:
    case_id: str
    kind: CaseKind
    workflow_id: str
    priority: int = 5
    correlation_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kind": self.kind.value,
            "workflow_id": self.workflow_id,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Case":
        return cls(
            case_id=data["case_id"],
            kind=CaseKind(data["kind"]),
            workflow_id=data["workflow_id"],
            priority=int(data.get("priority", 5)),
            correlation_id=data.get("correlation_id"),
            payload=dict(data.get("payload", {})),
            created_at=float(data.get("created_at", 0.0)),
        )


class CaseQueue:
    """
    workflow/case_queue/
      ready/    <priority>-<created_at>-<case_id>.json
      claimed/<worker_id>/
      done/
      failed/
    """

    def __init__(self, workflow_root: Path):
        self.root = Path(workflow_root).resolve() / "workflow" / "case_queue"
        for sub in ("ready", "claimed", "done", "failed"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def enqueue(self, kind: CaseKind, workflow_id: str, *,
                priority: int = 5,
                correlation_id: str | None = None,
                payload: dict[str, Any] | None = None) -> Case:
        case = Case(
            case_id=f"case-{uuid.uuid4().hex[:12]}",
            kind=kind,
            workflow_id=workflow_id,
            priority=priority,
            correlation_id=correlation_id,
            payload=payload or {},
            created_at=time.time(),
        )
        filename = f"{case.priority:02d}-{int(case.created_at):012d}-{case.case_id}.json"
        target = self.root / "ready" / filename
        _atomic_write(target, case.to_dict())
        return case

    def list_ready(self) -> list[Path]:
        return sorted((self.root / "ready").glob("*.json"))

    def claim(self, worker_id: str, *, limit: int = 1) -> list[Case]:
        claimed_dir = self.root / "claimed" / worker_id
        claimed_dir.mkdir(parents=True, exist_ok=True)
        result = []
        for p in self.list_ready():
            if len(result) >= limit:
                break
            target = claimed_dir / p.name
            try:
                os.replace(p, target)
            except FileNotFoundError:
                # 已被其他 worker 抢走
                continue
            except OSError:
                continue
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
            except FileNotFoundError:
                continue
            result.append(Case.from_dict(data))
        return result

    def mark_done(self, worker_id: str, case: Case) -> None:
        src = self.root / "claimed" / worker_id
        for f in src.glob(f"*-{case.case_id}.json"):
            os.replace(f, self.root / "done" / f.name)
            return
        raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"case not claimed: {case.case_id}")

    def mark_failed(self, worker_id: str, case: Case, reason: str) -> None:
        src = self.root / "claimed" / worker_id
        for f in src.glob(f"*-{case.case_id}.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_failure_reason"] = reason
            data["_failed_at"] = time.time()
            target = self.root / "failed" / f.name
            _atomic_write(target, data)
            f.unlink()
            return
        raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"case not claimed: {case.case_id}")


def _atomic_write(target: Path, data: dict[str, Any]) -> None:
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
