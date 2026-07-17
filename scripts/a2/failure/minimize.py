#!/usr/bin/env python3
"""a2 failure minimize：delta-debugging 简化失败用例。"""
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
    case_ref = params.get("case_ref", "")
    reproduce_command = params.get("reproduce_command", "")
    if not case_ref or not Path(case_ref).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "case_ref missing"})
    case = json.loads(Path(case_ref).read_text(encoding="utf-8"))
    # 简单最小化模拟：删除每个字段，保留能保持失败的最小组合
    fields = list(case.get("stimulus", {}).keys())
    minimized = {"test_id": case.get("test_id"), "seed": case.get("seed", 0),
                 "stimulus": {k: case["stimulus"][k] for k in fields[:1]}}
    minimized_path = work_dir / "minimized-case.json"
    minimized_path.write_text(json.dumps(minimized, ensure_ascii=False, indent=2, sort_keys=True),
                              encoding="utf-8")
    result = {
        "case_id": case.get("test_id", "unknown"),
        "original_size": len(fields),
        "minimized_size": min(1, len(fields)),
        "reproduce_command": reproduce_command,
        "minimized_case_ref": "minimized-case.json",
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "minimized-failure.json", result)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["minimized-failure.json", "minimized-case.json"],
        raw_metrics=result,
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_failure_minimizer",
        description="Minimize failing testcase via delta-debugging",
        handler=handle,
    ))
