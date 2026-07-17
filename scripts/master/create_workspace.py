#!/usr/bin/env python3
"""master_create_workspace：按 Gate 请求原子创建 Primary 或 Child Workspace。

用法（统一 CLI）：
  python3 scripts/master/create_workspace.py \
      --request-json <req> --result-json <res> --work-dir <dir> --timeout-s 60

Request 字段（interfaces/tools/master/master-create-workspace.schema.json）：
  parameters:
    workspace_type: primary | child-service | a3-candidate
    role: master | a1 | a2 | a3
    workflow_id
    workflow_round_id
    agent_instance_id?   (child-service)
    request_id?          (child-service)
    candidate_id?        (a3-candidate)
    product_run_root?    默认 CWD
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import to_posix_rel
from scripts.common.script_cli import ScriptResult, run_script
from dooragent.workspace.manager import WorkspaceManager


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    workspace_type = params.get("workspace_type", "primary")
    role = params.get("role")
    workflow_id = params.get("workflow_id")
    round_id = params.get("workflow_round_id")
    if not (role and workflow_id and round_id):
        return ScriptResult(
            status="failed",
            error_code="INVALID_REQUEST",
            error={"message": "role/workflow_id/workflow_round_id are required"},
        )
    product_run_root = Path(params.get("product_run_root") or REPO_ROOT)
    mgr = WorkspaceManager(product_run_root)
    if workspace_type == "primary":
        info = mgr.create_primary(
            workflow_id=workflow_id, workflow_round_id=round_id,
            role=role, agent_instance_id=params.get("agent_instance_id"),
        )
    elif workspace_type == "child-service":
        req_id = params.get("request_id")
        if not req_id:
            return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                                 error={"message": "request_id is required for child-service"})
        info = mgr.create_child_service(
            workflow_id=workflow_id, workflow_round_id=round_id,
            role=role, request_id=req_id,
            agent_instance_id=params.get("agent_instance_id"),
        )
    elif workspace_type == "a3-candidate":
        cand = params.get("candidate_id")
        if not cand:
            return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                                 error={"message": "candidate_id required for a3-candidate"})
        info = mgr.create_a3_candidate(
            workflow_id=workflow_id, workflow_round_id=round_id, candidate_id=cand,
        )
    else:
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                             error={"message": f"unknown workspace_type: {workspace_type}"})

    return ScriptResult(
        status="completed",
        output_artifact_refs=[info.workspace_path + "/manifest.json"],
        raw_metrics={
            "workspace_id": info.workspace_id,
            "workspace_path": info.workspace_path,
            "role": info.role,
            "kind": info.kind.value,
            "state": info.state.value,
        },
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="master_create_workspace",
        description="Create Primary or Child Service Workspace atomically",
        handler=handle,
    ))
