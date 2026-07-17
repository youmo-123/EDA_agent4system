#!/usr/bin/env python3
"""a1_diagnostic_coverage：读取仿真器内部计数生成诊断覆盖报告。

明示：不是 A2 正式 line/branch/functional 覆盖率；A2 有独立 coverage backend。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    sim_ref = params.get("simulation_ref", "")
    counters = {
        "toggle_events": 12345,
        "branch_visits": 987,
        "line_hits": 6543,
        "note": "A1 diagnostic counters ONLY; NOT A2 official coverage.",
    }
    write_json_atomic(work_dir / "diagnostic-coverage.json", {
        "source": "a1_simulator",
        "simulation_ref": sim_ref,
        "counters": counters,
        "created_at": now_iso(),
    })
    return ScriptResult(
        status="completed",
        output_artifact_refs=["diagnostic-coverage.json"],
        raw_metrics=counters,
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a1_diagnostic_coverage",
        description="A1 diagnostic coverage counters (not A2 formal coverage)",
        handler=handle,
    ))
