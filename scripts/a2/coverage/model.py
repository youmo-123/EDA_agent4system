#!/usr/bin/env python3
"""a2_coverage_model_generator：从 design.json + goals 生成 coverage-model。"""
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
    design_ref = params.get("design_ref", "")
    goals = params.get("goals") or {"line": 0.9, "branch": 0.85, "functional": 0.9}
    if not design_ref or not Path(design_ref).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "design_ref missing"})
    design = json.loads(Path(design_ref).read_text(encoding="utf-8"))
    ports = design.get("ports", [])
    bins = []
    for p in ports:
        if p["direction"] == "input":
            bins.append({
                "name": f"{p['name']}_toggle",
                "type": "signal_toggle",
                "port": p["name"],
                "width": p.get("width", 1),
                "sampling": "rising_edge_clock",
            })
    crosses = []
    if len(ports) >= 2:
        crosses.append({
            "name": "handshake_cross",
            "components": [p["name"] for p in ports[:2]],
            "sampling": "when-valid",
        })
    model = {
        "model_id": f"cov-model-{design.get('top', 'top')}-v1",
        "bins": bins,
        "crosses": crosses,
        "sampling_triggers": ["posedge clk"],
        "structural_metrics_requested": ["line", "branch"],
        "completion_goals": goals,
        "semantic_assumptions": ["ports parsed from RTL only; no protocol semantics assumed"],
        "created_at": now_iso(),
    }
    # 计算 model_hash
    import hashlib
    model_hash = hashlib.sha256(
        json.dumps({k: v for k, v in model.items() if k != "model_hash"},
                   sort_keys=True).encode("utf-8")
    ).hexdigest()
    model["model_hash"] = model_hash
    write_json_atomic(work_dir / "coverage-model.json", model)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["coverage-model.json"],
        raw_metrics={"bin_count": len(bins), "cross_count": len(crosses),
                     "model_hash": model_hash},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_coverage_model_generator",
        description="Emit coverage-model.json",
        handler=handle,
    ))
