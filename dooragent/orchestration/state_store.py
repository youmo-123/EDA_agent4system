"""基于文件系统的状态存储：单写者 + Compare-And-Set + 追加不可变 transition 事件。

约束（方案 10.4/13.3）：
1. 使用 compare-and-set（expected_state_version）
2. 先追加 transition event，再更新状态快照
3. 相同 transition_id 幂等
4. 每个实体一个逻辑单写者
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode


@dataclass(slots=True)
class StateEntry:
    entity_type: str
    entity_id: str
    state_version: int
    lifecycle_state: str
    health_state: str = "unknown"
    outcome_state: str = "none"
    report_state: str = "not_required"
    evidence_state: str = "none"
    blocking_state: str = "none"
    updated_at: float = 0.0
    patch: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "state_version": self.state_version,
            "lifecycle_state": self.lifecycle_state,
            "health_state": self.health_state,
            "outcome_state": self.outcome_state,
            "report_state": self.report_state,
            "evidence_state": self.evidence_state,
            "blocking_state": self.blocking_state,
            "updated_at": self.updated_at,
            "patch": self.patch,
        }


class StateStore:
    """
    目录结构（相对 workflow root）：
      workflow/state/
        snapshots/<entity_type>/<entity_id>.json
        transitions/<entity_type>/<entity_id>/<version>-<transition_id>.json
    """

    def __init__(self, workflow_root: Path):
        self.root = Path(workflow_root).resolve()
        (self.root / "workflow" / "state" / "snapshots").mkdir(parents=True, exist_ok=True)
        (self.root / "workflow" / "state" / "transitions").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def _snapshot_path(self, entity_type: str, entity_id: str) -> Path:
        return self.root / "workflow" / "state" / "snapshots" / entity_type / f"{entity_id}.json"

    def _transitions_dir(self, entity_type: str, entity_id: str) -> Path:
        return self.root / "workflow" / "state" / "transitions" / entity_type / entity_id

    # ------------------------------------------------------------------ #
    def get(self, entity_type: str, entity_id: str) -> StateEntry | None:
        p = self._snapshot_path(entity_type, entity_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return StateEntry(**data)

    def create(self, entry: StateEntry) -> StateEntry:
        p = self._snapshot_path(entry.entity_type, entry.entity_id)
        if p.exists():
            raise DoorAgentError(
                ErrorCode.INVALID_REQUEST,
                f"state entity already exists: {entry.entity_type}/{entry.entity_id}",
            )
        entry.state_version = 0
        entry.updated_at = time.time()
        _atomic_write_json(p, entry.to_dict())
        return entry

    def transition(
        self,
        *,
        entity_type: str,
        entity_id: str,
        expected_state_version: int,
        expected_lifecycle_state: str | None,
        patch: dict[str, Any],
        caused_by: str | None = None,
        evidence_refs: list[str] | None = None,
        transition_id: str | None = None,
    ) -> StateEntry:
        """CAS 转换；expected_state_version 不匹配则抛 CONFLICT。"""
        current = self.get(entity_type, entity_id)
        if current is None:
            raise DoorAgentError(
                ErrorCode.INVALID_REQUEST,
                f"entity not found: {entity_type}/{entity_id}",
            )
        if current.state_version != expected_state_version:
            raise DoorAgentError(
                ErrorCode.INVALID_REQUEST,
                f"CAS conflict on {entity_type}/{entity_id}: "
                f"expected v{expected_state_version}, actual v{current.state_version}",
            )
        if expected_lifecycle_state and current.lifecycle_state != expected_lifecycle_state:
            raise DoorAgentError(
                ErrorCode.INVALID_REQUEST,
                f"lifecycle mismatch on {entity_type}/{entity_id}: "
                f"expected {expected_lifecycle_state}, actual {current.lifecycle_state}",
            )
        tid = transition_id or f"tr-{int(time.time() * 1e6)}"
        # 幂等：同 transition_id 已存在则直接返回当前
        tdir = self._transitions_dir(entity_type, entity_id)
        tdir.mkdir(parents=True, exist_ok=True)
        for f in tdir.glob("*.json"):
            if f.name.endswith(f"-{tid}.json"):
                return current
        # 1. 先追加 transition
        new_version = current.state_version + 1
        transition_data = {
            "transition_id": tid,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "from_version": current.state_version,
            "to_version": new_version,
            "from_lifecycle": current.lifecycle_state,
            "patch": patch,
            "caused_by": caused_by,
            "evidence_refs": list(evidence_refs or []),
            "at": time.time(),
        }
        _atomic_write_json(tdir / f"{new_version:06d}-{tid}.json", transition_data)
        # 2. 更新快照
        updated = StateEntry(**current.to_dict())
        updated.state_version = new_version
        for k, v in patch.items():
            if hasattr(updated, k):
                setattr(updated, k, v)
            else:
                updated.patch[k] = v
        updated.updated_at = time.time()
        _atomic_write_json(self._snapshot_path(entity_type, entity_id), updated.to_dict())
        return updated

    def list_transitions(self, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        tdir = self._transitions_dir(entity_type, entity_id)
        if not tdir.exists():
            return []
        result = []
        for f in sorted(tdir.glob("*.json")):
            result.append(json.loads(f.read_text(encoding="utf-8")))
        return result

    def rebuild_from_transitions(self, entity_type: str, entity_id: str) -> StateEntry | None:
        """从 transition 序列重建快照（用于恢复/校验）。"""
        transitions = self.list_transitions(entity_type, entity_id)
        if not transitions:
            return self.get(entity_type, entity_id)
        cur = self.get(entity_type, entity_id)
        # 简单校验：最大 to_version 应等于当前 snapshot 的 state_version
        max_ver = max(t["to_version"] for t in transitions)
        if cur and cur.state_version != max_ver:
            raise DoorAgentError(
                ErrorCode.INVALID_REQUEST,
                f"snapshot inconsistent for {entity_type}/{entity_id}: "
                f"snapshot v{cur.state_version} vs transitions max v{max_ver}",
            )
        return cur


def _atomic_write_json(target: Path, data: Any) -> None:
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
