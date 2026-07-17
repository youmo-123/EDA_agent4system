#!/usr/bin/env python3
"""master_archive_round：冻结轮次 Workspace 并生成 archive manifest。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso, sha256_file
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    workflow_root = Path(params.get("workflow_root") or "")
    round_id = params.get("workflow_round_id")
    if not (workflow_root.exists() and round_id):
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "workflow_root and workflow_round_id required"})
    ws_root = workflow_root / "workspaces" / round_id
    if not ws_root.exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": f"round workspaces not found: {ws_root}"})
    manifest = {"workflow_round_id": round_id, "archived_at": now_iso(), "workspaces": []}
    for ws in sorted(ws_root.iterdir()):
        if not ws.is_dir():
            continue
        mp = ws / "manifest.json"
        if not mp.exists():
            continue
        data = json.loads(mp.read_text(encoding="utf-8"))
        data["state"] = "FROZEN"
        write_json_atomic(mp, data)
        manifest["workspaces"].append({
            "name": ws.name,
            "manifest_hash": sha256_file(mp),
            "path": str(ws.relative_to(workflow_root).as_posix()),
        })
    archive_path = work_dir / "archive-manifest.json"
    write_json_atomic(archive_path, manifest)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["archive-manifest.json"],
        raw_metrics={"workspace_count": len(manifest["workspaces"])},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="master_archive_round",
        description="Freeze round and produce archive manifest",
        handler=handle,
    ))
