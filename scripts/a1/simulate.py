#!/usr/bin/env python3
"""a1_simulate：调用自研仿真器执行 TB/tests/seed。

Request parameters:
  compile_ref: str
  tests_ref: str (指向一个 test 列表 JSON 文件；若不存在则用 default)
  seed: int
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.a1.core.mock_simulator import is_real_simulator_available, mock_simulate
from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    tests_ref = params.get("tests_ref")
    seed = int(params.get("seed", 1))
    tests: list[str] = []
    if tests_ref and Path(tests_ref).exists():
        try:
            data = json.loads(Path(tests_ref).read_text(encoding="utf-8"))
            if isinstance(data, list):
                tests = data
            elif isinstance(data, dict) and "tests" in data:
                tests = list(data["tests"])
        except Exception:
            tests = ["default"]
    else:
        tests = ["default"]

    if is_real_simulator_available():
        return ScriptResult(
            status="unavailable", error_code="TOOL_NOT_IMPLEMENTED",
            error={"message": "real simulator adapter not implemented in scaffold"},
        )

    sim = mock_simulate(tests=tests, seed=seed)
    evidence = {
        "run_id": f"sim-{seed}-{len(tests)}",
        "tb_ref": params.get("compile_ref", "unknown"),
        "tests_ref": tests_ref or "inline-default",
        "commands": ["mock_simulator"],
        "exit_code": 0,
        "pass_count": sim.pass_count,
        "fail_count": sim.fail_count,
        "seed": seed,
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "simulation-run.json", evidence)
    write_json_atomic(work_dir / "profile-raw.json", {
        "events_processed": sim.events_processed,
        "delta_cycles": sim.delta_cycles,
        "wall_time_s": sim.wall_time_s,
        "module_time_s": sim.module_time_s,
    })
    status = "completed" if sim.fail_count == 0 else "partial"
    return ScriptResult(
        status=status,
        error_code=None if status == "completed" else "A1_SIMULATION_FAILED",
        output_artifact_refs=["simulation-run.json", "profile-raw.json"],
        raw_metrics={"pass": sim.pass_count, "fail": sim.fail_count,
                     "events": sim.events_processed},
        tool_versions={"backend": "mock-a1-simulator"},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a1_simulate", description="A1 event-driven simulation",
        handler=handle,
    ))
