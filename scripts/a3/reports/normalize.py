#!/usr/bin/env python3
"""a3 reports/normalize：把原始综合/时序报告统一成 A3 报告片段。"""
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


def _read_json(p: str) -> dict:
    if not p or not Path(p).exists():
        return {}
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    synth = _read_json(params.get("synth_ref", ""))
    timing = _read_json(params.get("timing_ref", ""))
    search = _read_json(params.get("search_ref", ""))
    unified = {
        "created_at": now_iso(),
        "synth": {
            "netlist_hash": synth.get("netlist_hash") or (synth.get("raw_metrics") or {}).get("netlist_hash"),
            "tool_versions": synth.get("tool_versions", {}),
        },
        "timing": {
            "arrival": timing.get("arrival"),
            "slack": timing.get("slack"),
            "backend": timing.get("backend"),
        },
        "search": {
            "experiment_id": search.get("experiment_id"),
            "fallback_triggered": search.get("fallback_triggered", False),
        },
        "notes": "unified A3 report fragment",
    }
    write_json_atomic(work_dir / "a3-report-fragment.json", unified)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["a3-report-fragment.json"],
        raw_metrics={"has_synth": bool(synth), "has_timing": bool(timing)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_reports_normalize",
        description="Normalize synth/timing/search reports",
        handler=handle,
    ))
