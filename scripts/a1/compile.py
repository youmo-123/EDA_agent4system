#!/usr/bin/env python3
"""a1_compile：把结构化请求转换为自研编译器 CLI；不可用时降级为 Mock 内核。

Request parameters:
  rtl_refs: [str]        RTL 文件路径
  top: str
  filelist: [str] | null
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.a1.core.mock_simulator import is_real_simulator_available, mock_compile
from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    rtl_refs = params.get("rtl_refs") or []
    top = params.get("top") or ""
    if not rtl_refs or not top:
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "rtl_refs and top required"})

    if is_real_simulator_available():
        return ScriptResult(
            status="unavailable", error_code="TOOL_NOT_IMPLEMENTED",
            error={"message": "real simulator adapter not implemented in scaffold"},
        )

    result = mock_compile(rtl_refs, top)
    if not result.ok:
        write_json_atomic(work_dir / "compile-report.json", {
            "status": "failed",
            "errors": result.error_lines,
            "created_at": now_iso(),
        })
        return ScriptResult(
            status="failed", error_code="A1_COMPILE_FAILED",
            error={"messages": result.error_lines},
            output_artifact_refs=["compile-report.json"],
        )
    write_json_atomic(work_dir / "compile-report.json", {
        "status": "completed",
        "top": top,
        "files": rtl_refs,
        "source_map": result.source_map,
        "backend": "mock",
        "created_at": now_iso(),
    })
    write_json_atomic(work_dir / "source-map.json", result.source_map)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["compile-report.json", "source-map.json"],
        tool_versions={"backend": "mock-a1-simulator"},
        raw_metrics={"file_count": len(rtl_refs)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a1_compile", description="A1 compile RTL files",
        handler=handle,
    ))
