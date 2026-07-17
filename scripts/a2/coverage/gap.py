#!/usr/bin/env python3
"""a2 coverage gap analyzer：解读 coverage-result 并产出 gap 分析。"""
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
from dooragent.agents.a2.policy import A2Policy


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    coverage_result_ref = params.get("coverage_result_ref", "")
    if not coverage_result_ref or not Path(coverage_result_ref).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "coverage_result_ref missing"})
    cov = json.loads(Path(coverage_result_ref).read_text(encoding="utf-8"))
    metrics = cov.get("metrics", {})
    reachable_gaps = [k for k, v in metrics.items() if 0 < v < 1]
    unreachable = []
    observability = []
    if metrics.get("functional", 0.0) == 0.0:
        # 全 0：优先怀疑激励不足；提示需要 request-info 或 constraint-solver
        unreachable.append({"metric": "functional", "reason": "no hits at all"})
    priority = [{"metric": k, "value": v} for k, v in metrics.items() if v < 0.9]

    policy = A2Policy()
    strategy = policy.next_generation_strategy({
        "reachable_gaps": reachable_gaps,
        "suspected_unreachable": unreachable,
        "observability_gaps": observability,
    })
    gap = {
        "coverage_result_ref": coverage_result_ref,
        "reachable_gaps": reachable_gaps,
        "suspected_unreachable": unreachable,
        "observability_gaps": observability,
        "priority_targets": priority,
        "selected_generation_strategy": strategy,
        "next_test_plan": {"strategy": strategy, "budget": {"count": 1000}},
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "coverage-gap-analysis.json", gap)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["coverage-gap-analysis.json"],
        raw_metrics={"strategy": strategy, "reachable": len(reachable_gaps)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_coverage_gap_analyzer",
        description="Explain coverage result & pick next strategy",
        handler=handle,
    ))
