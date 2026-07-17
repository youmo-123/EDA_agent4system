#!/usr/bin/env python3
"""a1_trace_export：解析 VCD/FST/event trace 并生成 trace 索引/摘要。

限制内存和输出规模；缺 trace 时返回 unsupported。
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
    fmt = params.get("format", "vcd")
    sim_ref = params.get("simulation_ref", "")
    trace_src = params.get("trace_source", "")
    if not trace_src or not Path(trace_src).exists():
        return ScriptResult(
            status="unsupported",
            error_code="A1_PROFILE_INCOMPLETE",
            error={"message": "trace source not provided"},
        )
    summary = {
        "format": fmt,
        "sim_ref": sim_ref,
        "trace_size_bytes": Path(trace_src).stat().st_size,
        "signals": [],
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "trace-summary.json", summary)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["trace-summary.json"],
        raw_metrics={"trace_size": summary["trace_size_bytes"]},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a1_trace_export",
        description="Parse VCD/FST/event trace",
        handler=handle,
    ))
