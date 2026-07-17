#!/usr/bin/env python3
"""a1_profile_metrics：聚合事件/delta/模块耗时/内存/队列/线程指标。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    sim_ref = params.get("simulation_ref", "")
    # 若上一步落了 profile-raw.json，可直接读；否则给出保守 Mock 汇总
    raw = {}
    if sim_ref and Path(sim_ref).exists():
        try:
            raw = json.loads(Path(sim_ref).read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    profile = {
        "events_processed": raw.get("events_processed", 0),
        "delta_cycles": raw.get("delta_cycles", 0),
        "wall_time_s": raw.get("wall_time_s", 0.0),
        "peak_memory_mb": raw.get("peak_memory_mb", 0),
        "module_time_s": raw.get("module_time_s", {}),
        "queue_depth_max": raw.get("queue_depth_max", 0),
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "profile-report.json", profile)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["profile-report.json"],
        raw_metrics=profile,
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a1_profile_metrics",
        description="Aggregate profile telemetry",
        handler=handle,
    ))
