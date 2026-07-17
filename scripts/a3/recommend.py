#!/usr/bin/env python3
"""a3 recommend：把 hotspot + Pareto 转为结构化 RTL 优化建议。"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import now_iso
from scripts.common.atomic_io import write_json_atomic
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    hotspot_ref = params.get("hotspot_ref", "")
    pareto_ref = params.get("pareto_ref", "")
    hotspots = []
    if hotspot_ref and Path(hotspot_ref).exists():
        try:
            hotspots = json.loads(Path(hotspot_ref).read_text(encoding="utf-8")).get("items", [])
        except Exception:
            hotspots = []

    changes = []
    risks = []
    for h in hotspots[:3]:
        kind = h.get("kind", "")
        if kind == "negative_slack":
            changes.append({
                "target": "critical_path",
                "recommendation": "pipeline the longest combinational path or increase clock period",
                "expected_delta_ns": abs(float(h.get("slack", 0.0))),
            })
            risks.append({"kind": "functional_change",
                          "note": "pipelining changes latency; must regress"})
        if kind == "area_baseline":
            changes.append({
                "target": "logic_sharing",
                "recommendation": "explore common-subexpression sharing to reduce area",
                "expected_delta_area": -0.05,
            })
    suggestion = {
        "suggestion_id": f"sug-{uuid.uuid4().hex[:8]}",
        "changes": changes,
        "risks": risks,
        "expected_impact": {"area_ratio": -0.05 if any(c.get("expected_delta_area") for c in changes) else 0.0,
                             "arrival_ns": -sum(c.get("expected_delta_ns", 0.0) for c in changes)},
        "regression_plan": {"required": True, "coverage_reuse": True,
                            "must_pass": ["a2_existing_tests"]},
        "created_at": now_iso(),
        "pareto_ref": pareto_ref,
    }
    write_json_atomic(work_dir / "rtl-optimization-suggestion.json", suggestion)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["rtl-optimization-suggestion.json"],
        raw_metrics={"changes": len(changes)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_rtl_recommender",
        description="Turn hotspots+Pareto into structured RTL suggestion",
        handler=handle,
    ))
