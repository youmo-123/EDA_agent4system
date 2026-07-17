#!/usr/bin/env python3
"""a2_simulation_coverage：调用 A2 Simulation Backend 采集覆盖证据。

- 默认 backend=mock，仅生成协议一致的 simulation-run，不冒充覆盖率
- 真实场景应通过 backend=vcs/urg/cocotb 等注册后端；未注册返回 UNAVAILABLE
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso
from scripts.common.script_cli import ScriptResult, run_script


ALLOWED_BACKENDS = {"mock", "cocotb", "vcs", "verilator"}


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    tb_ref = params.get("tb_ref")
    tests_ref = params.get("tests_ref")
    backend = params.get("backend", "mock")
    if backend not in ALLOWED_BACKENDS:
        return ScriptResult(status="unsupported", error_code="INVALID_REQUEST",
                            error={"message": f"unknown backend: {backend}"})
    if backend != "mock":
        # 真实 backend 未接入
        return ScriptResult(status="unavailable", error_code="CAPABILITY_UNAVAILABLE",
                            error={"message": f"backend {backend} not bound in scaffold"})
    if not tests_ref or not Path(tests_ref).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "tests_ref missing"})
    tests = json.loads(Path(tests_ref).read_text(encoding="utf-8"))
    entries = tests.get("entries", []) if isinstance(tests, dict) else tests
    pass_count = len(entries)
    run = {
        "run_id": f"a2sim-{tests.get('manifest_id', 'inline')}",
        "tb_ref": tb_ref or "unknown",
        "tests_ref": tests_ref,
        "commands": ["mock_a2_sim"],
        "exit_code": 0,
        "pass_count": pass_count,
        "fail_count": 0,
        "backend": backend,
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "simulation-run.json", run)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["simulation-run.json"],
        raw_metrics={"pass": pass_count},
        tool_versions={"backend": backend},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_simulation_coverage",
        description="Run A2 simulation via configured backend",
        handler=handle,
    ))
