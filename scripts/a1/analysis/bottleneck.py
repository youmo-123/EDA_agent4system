#!/usr/bin/env python3
"""a1_bottleneck_analyzer：聚合 profile/trace 识别仿真瓶颈。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    profile_ref = params.get("profile_ref", "")
    trace_ref = params.get("trace_ref")

    profile = {}
    if profile_ref and Path(profile_ref).exists():
        try:
            profile = json.loads(Path(profile_ref).read_text(encoding="utf-8"))
        except Exception:
            profile = {}
    if not profile:
        return ScriptResult(status="unsupported",
                            error_code="A1_PROFILE_INCOMPLETE",
                            error={"message": "profile_ref missing or unreadable"})

    module_time = profile.get("module_time_s", {})
    sorted_mods = sorted(module_time.items(), key=lambda kv: kv[1], reverse=True)
    top_items = sorted_mods[:5]
    items = [
        {
            "kind": "module_hot_path",
            "module": m,
            "wall_time_s": t,
            "confidence": "medium",
            "based_on": ["profile"],
        }
        for m, t in top_items
    ]
    report = {
        "items": items,
        "profile_ref": profile_ref,
        "trace_ref": trace_ref,
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "bottleneck-report.json", report)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["bottleneck-report.json"],
        raw_metrics={"item_count": len(items)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a1_bottleneck_analyzer",
        description="Aggregate profile/trace to locate simulation bottlenecks",
        handler=handle,
    ))
