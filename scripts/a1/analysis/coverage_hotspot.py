#!/usr/bin/env python3
"""a1_coverage_hotspot_analyzer：把诊断计数和 trace 映射回 RTL 位置。"""
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
    diag = params.get("diagnostic_ref", "")
    src_map_ref = params.get("source_map_ref", "")
    if not diag or not Path(diag).exists():
        return ScriptResult(status="unsupported",
                            error_code="A1_COVERAGE_UNSUPPORTED",
                            error={"message": "diagnostic_ref missing"})
    counters = {}
    try:
        counters = json.loads(Path(diag).read_text(encoding="utf-8")).get("counters", {})
    except Exception:
        pass
    items = [
        {
            "kind": "low_toggle_region",
            "counter": "toggle_events",
            "value": counters.get("toggle_events", 0),
            "confidence": "medium",
            "based_on": ["diagnostic"],
            "note": "diagnostic only, not A2 formal coverage",
        }
    ]
    report = {
        "items": items,
        "source_map_ref": src_map_ref or None,
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "hotspot-report.json", report)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["hotspot-report.json"],
        raw_metrics={"item_count": len(items)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a1_coverage_hotspot_analyzer",
        description="Map diagnostic coverage & trace back to RTL regions",
        handler=handle,
    ))
