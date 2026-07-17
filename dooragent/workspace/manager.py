"""Workspace 管理器：创建 Primary/Child Workspace 并落 manifest。

runs/<workflow_id>/
  workflow/
  workspaces/<workflow_round_id>/
    master/
    a1-primary/  a1-service-<request_id>/
    a2-primary/
    a3-primary/  a3-candidate-<candidate_id>/
  exchange/
  artifacts/
  outputs/
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode
from dooragent.runtime.paths import ensure_relative_posix, resolve_under


class WorkspaceKind(StrEnum):
    PRIMARY = "primary"
    CHILD_SERVICE = "child-service"


class WorkspaceState(StrEnum):
    CREATING = "CREATING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    ARCHIVING = "ARCHIVING"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


@dataclass(slots=True)
class WorkspaceInfo:
    workspace_id: str
    workspace_path: str  # 相对 product_run_root
    role: str
    kind: WorkspaceKind
    state: WorkspaceState
    workflow_id: str
    workflow_round_id: str
    agent_instance_id: str | None
    created_at: str


class WorkspaceManager:
    """基于文件系统的 Workspace 管理器。

    - 所有路径都相对 `product_run_root`；写入前经过 `ensure_relative_posix` 校验
    - 使用 os.makedirs(exist_ok=False) 以避免误覆盖已有 Workspace
    """

    LAYOUT = {
        "inputs": "inputs",
        "artifacts": "artifacts",
        "logs": "logs",
        "state": "state",
        "exchange": "exchange",
    }

    def __init__(self, product_run_root: Path):
        self.root = product_run_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def workflow_root(self, workflow_id: str) -> Path:
        _validate_id(workflow_id, "workflow_id")
        return self.root / "runs" / workflow_id

    def _workspaces_root(self, workflow_id: str, round_id: str) -> Path:
        _validate_id(round_id, "workflow_round_id")
        return self.workflow_root(workflow_id) / "workspaces" / round_id

    # ------------------------------------------------------------------ #
    def create_primary(
        self,
        *,
        workflow_id: str,
        workflow_round_id: str,
        role: str,
        agent_instance_id: str | None = None,
    ) -> WorkspaceInfo:
        _validate_role(role)
        workspaces_root = self._workspaces_root(workflow_id, workflow_round_id)
        name = "master" if role == "master" else f"{role}-primary"
        ws_path = workspaces_root / name
        return self._create(
            workflow_id=workflow_id,
            workflow_round_id=workflow_round_id,
            role=role,
            kind=WorkspaceKind.PRIMARY,
            path=ws_path,
            agent_instance_id=agent_instance_id,
        )

    def create_child_service(
        self,
        *,
        workflow_id: str,
        workflow_round_id: str,
        role: str,
        request_id: str,
        agent_instance_id: str | None = None,
    ) -> WorkspaceInfo:
        _validate_role(role)
        _validate_id(request_id, "request_id")
        workspaces_root = self._workspaces_root(workflow_id, workflow_round_id)
        ws_path = workspaces_root / f"{role}-service-{request_id}"
        return self._create(
            workflow_id=workflow_id,
            workflow_round_id=workflow_round_id,
            role=role,
            kind=WorkspaceKind.CHILD_SERVICE,
            path=ws_path,
            agent_instance_id=agent_instance_id,
        )

    def create_a3_candidate(
        self,
        *,
        workflow_id: str,
        workflow_round_id: str,
        candidate_id: str,
    ) -> WorkspaceInfo:
        _validate_id(candidate_id, "candidate_id")
        workspaces_root = self._workspaces_root(workflow_id, workflow_round_id)
        ws_path = workspaces_root / f"a3-candidate-{candidate_id}"
        return self._create(
            workflow_id=workflow_id,
            workflow_round_id=workflow_round_id,
            role="a3",
            kind=WorkspaceKind.CHILD_SERVICE,
            path=ws_path,
            agent_instance_id=None,
        )

    # ------------------------------------------------------------------ #
    def freeze(self, ws: WorkspaceInfo) -> WorkspaceInfo:
        self._write_manifest(ws, state=WorkspaceState.FROZEN)
        ws.state = WorkspaceState.FROZEN
        return ws

    def archive(self, ws: WorkspaceInfo) -> WorkspaceInfo:
        self._write_manifest(ws, state=WorkspaceState.ARCHIVED)
        ws.state = WorkspaceState.ARCHIVED
        return ws

    # ------------------------------------------------------------------ #
    def _create(
        self,
        *,
        workflow_id: str,
        workflow_round_id: str,
        role: str,
        kind: WorkspaceKind,
        path: Path,
        agent_instance_id: str | None,
    ) -> WorkspaceInfo:
        if path.exists():
            # 允许幂等：路径已存在但为 READY 时视作重入
            manifest_path = path / "manifest.json"
            if manifest_path.exists():
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                return _from_manifest(data)
            raise DoorAgentError(
                ErrorCode.INVALID_REQUEST,
                f"workspace path exists without manifest: {path}",
            )
        path.mkdir(parents=True, exist_ok=False)
        for sub in self.LAYOUT.values():
            (path / sub).mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        rel = path.relative_to(self.root).as_posix()
        ensure_relative_posix(rel)
        info = WorkspaceInfo(
            workspace_id=f"{workflow_round_id}-{role}-{path.name}",
            workspace_path=rel,
            role=role,
            kind=kind,
            state=WorkspaceState.READY,
            workflow_id=workflow_id,
            workflow_round_id=workflow_round_id,
            agent_instance_id=agent_instance_id,
            created_at=now,
        )
        self._write_manifest(info, state=WorkspaceState.READY)
        return info

    def _write_manifest(self, info: WorkspaceInfo, *, state: WorkspaceState) -> None:
        target_dir = self.root / info.workspace_path
        payload = {
            "workspace_id": info.workspace_id,
            "workspace_path": info.workspace_path,
            "role": info.role,
            "kind": info.kind.value,
            "state": state.value,
            "workflow_id": info.workflow_id,
            "workflow_round_id": info.workflow_round_id,
            "agent_instance_id": info.agent_instance_id,
            "created_at": info.created_at,
            "layout": dict(self.LAYOUT),
        }
        manifest_path = target_dir / "manifest.json"
        partial = manifest_path.with_suffix(".partial")
        partial.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            with partial.open("rb") as fh:
                os.fsync(fh.fileno())
        except OSError:  # pragma: no cover - windows may not allow
            pass
        os.replace(partial, manifest_path)


def _from_manifest(data: dict[str, Any]) -> WorkspaceInfo:
    return WorkspaceInfo(
        workspace_id=data["workspace_id"],
        workspace_path=data["workspace_path"],
        role=data["role"],
        kind=WorkspaceKind(data["kind"]),
        state=WorkspaceState(data["state"]),
        workflow_id=data["workflow_id"],
        workflow_round_id=data["workflow_round_id"],
        agent_instance_id=data.get("agent_instance_id"),
        created_at=data["created_at"],
    )


def _validate_id(value: str, field: str) -> None:
    if not value or not isinstance(value, str):
        raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"invalid {field}")
    if "/" in value or ".." in value or " " in value:
        raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"illegal chars in {field}: {value}")


def _validate_role(role: str) -> None:
    if role not in {"master", "a1", "a2", "a3"}:
        raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"invalid role: {role}")
