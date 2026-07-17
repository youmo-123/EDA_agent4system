#!/usr/bin/env python3
"""a2 functional coverage：聚合每个 bin 的 hits/total/uncovered。"""
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
    coverage_model_ref = params.get("coverage_model_ref", "")
    sampling_ref = params.get("sampling_ref")
    if not coverage_model_ref or not Path(coverage_model_ref).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "coverage_model_ref missing"})
    model = json.loads(Path(coverage_model_ref).read_text(encoding="utf-8"))
    bins = model.get("bins", [])
    # 无真实采样源：所有 bin hits=0 并显式声明
    aggregated = []
    total = len(bins)
    covered = 0
    for b in bins:
        aggregated.append({"name": b["name"], "hits": 0, "total": 1, "uncovered": True})
    metrics = {
        "bin_total": total,
        "bin_covered": covered,
        "functional_rate": (covered / total) if total else 0.0,
    }
    fc = {
        "model_id": model.get("model_id"),
        "metrics": metrics,
        "aggregated": aggregated,
        "raw_samples_ref": sampling_ref,
        "note": "No real sampling backend attached; hits=0 by construction",
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "functional-coverage.json", fc)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["functional-coverage.json"],
        raw_metrics=metrics,
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_functional_coverage",
        description="Aggregate functional bin hits",
        handler=handle,
    ))
