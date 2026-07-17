#!/usr/bin/env python3
"""a3 analysis/cost：把候选评价归一化 + Pareto 筛选。"""
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
from scripts.a3.search.pareto import is_dominated, non_dominated_set


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    candidates = params.get("candidate_results") or []
    valid = [c for c in candidates if c.get("validation_state") != "invalid"]
    nd = non_dominated_set(valid)
    results = []
    for c in valid:
        state = "non-dominated" if c in nd else "dominated"
        results.append({
            "candidate_id": c.get("candidate_id"),
            "cost_vector": {"area": c.get("area"), "arrival": c.get("arrival"),
                             "slack": c.get("slack"), "runtime_s": c.get("runtime_s")},
            "pareto_state": state,
        })
    payload = {"candidates": results, "pareto_count": len(nd), "created_at": now_iso()}
    write_json_atomic(work_dir / "pareto-archive.json", payload)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["pareto-archive.json"],
        raw_metrics={"pareto_count": len(nd), "total": len(valid)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_cost_model",
        description="Normalize costs and update 2D Pareto",
        handler=handle,
    ))
