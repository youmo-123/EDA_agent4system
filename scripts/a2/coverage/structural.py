#!/usr/bin/env python3
"""a2 structural coverage：归一化 line/branch 结构覆盖率。

- 后端未接入时返回 unavailable
"""
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
    backend = params.get("backend", "mock")
    raw_report_ref = params.get("raw_report_ref")

    if backend not in ("mock",):
        return ScriptResult(status="unavailable", error_code="CAPABILITY_UNAVAILABLE",
                            error={"message": f"structural coverage backend '{backend}' not bound"})

    if raw_report_ref and Path(raw_report_ref).exists():
        report = json.loads(Path(raw_report_ref).read_text(encoding="utf-8"))
    else:
        report = {"line": 0.0, "branch": 0.0, "note": "no raw report; mock zeros"}
    coverage = {
        "metrics": {
            "line": float(report.get("line", 0.0)),
            "branch": float(report.get("branch", 0.0)),
        },
        "backend": backend,
        "raw_report_ref": raw_report_ref,
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "structural-coverage.json", coverage)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["structural-coverage.json"],
        raw_metrics=coverage["metrics"],
        tool_versions={"backend": backend},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_structural_coverage",
        description="Normalize structural coverage report",
        handler=handle,
    ))
