#!/usr/bin/env python3
"""a3 analysis/hotspots：把关键路径/高面积单元回溯到 RTL 区域。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import now_iso
from scripts.common.atomic_io import write_json_atomic
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    synth_ref = params.get("synth_report_ref", "")
    timing_ref = params.get("timing_report_ref", "")
    source_map_ref = params.get("source_map_ref")

    items = []
    if timing_ref and Path(timing_ref).exists():
        try:
            tr = json.loads(Path(timing_ref).read_text(encoding="utf-8"))
            if tr.get("slack") is not None and float(tr["slack"]) < 0:
                items.append({
                    "kind": "negative_slack",
                    "slack": tr["slack"],
                    "confidence": "high",
                    "based_on": ["timing"],
                    "note": "Improve critical path or relax constraint",
                })
        except Exception:
            pass
    if synth_ref and Path(synth_ref).exists():
        try:
            sr = json.loads(Path(synth_ref).read_text(encoding="utf-8"))
            if sr.get("area") is not None and sr["area"] > 0:
                items.append({
                    "kind": "area_baseline",
                    "area": sr["area"],
                    "confidence": "medium",
                    "based_on": ["synth"],
                })
        except Exception:
            pass
    report = {"items": items, "source_map_ref": source_map_ref, "created_at": now_iso()}
    write_json_atomic(work_dir / "hotspot-report.json", report)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["hotspot-report.json"],
        raw_metrics={"item_count": len(items)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_hotspot_localizer",
        description="Map high-area cells / critical path to RTL",
        handler=handle,
    ))
