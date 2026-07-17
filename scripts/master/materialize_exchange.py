#!/usr/bin/env python3
"""master_materialize_exchange：把 artifact 引用原子发布到 exchange/。

- 校验路由矩阵、Schema、hash
- 按内容 hash 存储 blob
- 输出 exchange manifest
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.script_cli import ScriptResult, run_script
from dooragent.orchestration.exchange import ExchangeEntry, ExchangeManager


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    workflow_root = Path(params.get("workflow_root") or "")
    entries_raw = params.get("entries") or []
    if not workflow_root.exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                             error={"message": f"workflow_root not exist: {workflow_root}"})
    entries = []
    for e in entries_raw:
        entries.append(ExchangeEntry(
            artifact_type=e["artifact_type"],
            source_path=e["source_path"],
            producer_agent_instance_id=e["producer_agent_instance_id"],
            rtl_version_id=e.get("rtl_version_id"),
            workflow_id=e["workflow_id"],
            workflow_round_id=e["workflow_round_id"],
            hash=e.get("hash", ""),
        ))
    mgr = ExchangeManager(workflow_root)
    manifest = mgr.publish(entries)
    return ScriptResult(
        status="completed",
        output_artifact_refs=[f"exchange/manifests/{manifest['manifest_id']}.json"],
        raw_metrics={
            "manifest_id": manifest["manifest_id"],
            "count": len(manifest["entries"]),
        },
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="master_materialize_exchange",
        description="Publish read-only exchange package atomically",
        handler=handle,
    ))
