#!/usr/bin/env python3
"""a2 reports：汇总覆盖结果和 A2 run report。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso, sha256_file
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    coverage_model = params.get("coverage_model_ref", "")
    functional = params.get("functional_coverage_ref", "")
    structural = params.get("structural_coverage_ref")
    a1_gate = params.get("a1_function_gate_ref")
    phase_status = params.get("phase_status") or {}
    reproduce_commands = params.get("reproduce_commands") or []
    backend_versions = params.get("backend_versions") or {}

    if not coverage_model or not Path(coverage_model).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "coverage_model_ref missing"})
    if not functional or not Path(functional).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "functional_coverage_ref missing"})

    fc = json.loads(Path(functional).read_text(encoding="utf-8"))
    sc = {}
    if structural and Path(structural).exists():
        sc = json.loads(Path(structural).read_text(encoding="utf-8"))
    metrics = {
        "line": (sc.get("metrics") or {}).get("line", 0.0),
        "branch": (sc.get("metrics") or {}).get("branch", 0.0),
        "functional": (fc.get("metrics") or {}).get("functional_rate", 0.0),
    }
    coverage_result = {
        "coverage_model_ref": coverage_model,
        "test_batch_id": params.get("test_batch_id"),
        "metrics": metrics,
        "aggregate_metrics": metrics,
        "structural_evidence_refs": [structural] if structural else [],
        "functional_evidence_refs": [functional],
        "a1_function_gate_ref": a1_gate,
        "created_at": now_iso(),
    }
    import hashlib
    report_hash = hashlib.sha256(json.dumps(coverage_result, sort_keys=True).encode("utf-8")).hexdigest()
    coverage_result["report_hash"] = report_hash

    run_report = {
        "run_id": params.get("run_id") or "a2-run",
        "phase_status": phase_status,
        "reproduce_commands": reproduce_commands,
        "backend_versions": backend_versions,
        "failures": params.get("failures") or [],
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "coverage-result.json", coverage_result)
    write_json_atomic(work_dir / "run-report.json", run_report)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["coverage-result.json", "run-report.json"],
        raw_metrics=metrics,
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_report_emitter",
        description="Emit coverage-result + run-report",
        handler=handle,
    ))
