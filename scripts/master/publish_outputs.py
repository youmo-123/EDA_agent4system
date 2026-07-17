#!/usr/bin/env python3
"""master_publish_outputs：单写者发布最终报告、Pareto、决策清单。

- 防止旧 RTL 覆盖新版本（版本号严格递增）
- 输出 outputs/artifact-manifest.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import now_iso, sha256_file, to_posix_rel
from scripts.common.atomic_io import write_json_atomic
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    workflow_root = Path(params.get("workflow_root") or "")
    outputs = params.get("outputs") or {}     # 例如 {final_report: path, final_report_md: path, decision: path}
    rtl_version_id = params.get("rtl_version_id")
    if not workflow_root.exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "workflow_root missing"})

    outputs_dir = workflow_root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = outputs_dir / "artifact-manifest.json"
    existing = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"versions": []}

    # 单写者串行化：确保 rtl_version_id 单调递增
    if rtl_version_id and existing.get("versions"):
        last = existing["versions"][-1].get("rtl_version_id", "")
        if rtl_version_id < last:
            return ScriptResult(status="failed", error_code="STALE_RTL_VERSION",
                                error={"message": f"stale rtl_version_id {rtl_version_id} < {last}"})

    entries = []
    for kind, src_str in outputs.items():
        src = Path(src_str)
        if not src.exists():
            return ScriptResult(status="failed", error_code="ARTIFACT_MISSING",
                                error={"message": f"{kind}: {src} not found"})
        dst = outputs_dir / src.name
        dst.write_bytes(src.read_bytes())
        entries.append({
            "artifact_type": kind,
            "path": to_posix_rel(dst, workflow_root),
            "hash": sha256_file(dst),
            "bytes": dst.stat().st_size,
        })
    existing["versions"].append({
        "rtl_version_id": rtl_version_id,
        "published_at": now_iso(),
        "entries": entries,
    })
    write_json_atomic(manifest_path, existing)
    return ScriptResult(
        status="completed",
        output_artifact_refs=[to_posix_rel(manifest_path, workflow_root)],
        raw_metrics={"published": len(entries)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="master_publish_outputs",
        description="Publish final report/Pareto/decision as single writer",
        handler=handle,
    ))
