#!/usr/bin/env python3
"""a1_source_map：内部对象到 RTL 文件/实例/信号/源码位置的映射。"""
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


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    compile_ref = params.get("compile_ref", "")
    src_map = {}
    if compile_ref and Path(compile_ref).exists():
        try:
            data = json.loads(Path(compile_ref).read_text(encoding="utf-8"))
            src_map = data.get("source_map") or {}
        except Exception:
            src_map = {}
    if not src_map:
        return ScriptResult(status="unsupported", error_code="A1_COVERAGE_UNSUPPORTED",
                            error={"message": "compile_ref missing or has no source_map"})
    payload = {
        "source_map": src_map,
        "compile_ref": compile_ref,
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "source-map.json", payload)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["source-map.json"],
        raw_metrics={"module_count": len(src_map)},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a1_source_map",
        description="Emit source map from compiler output",
        handler=handle,
    ))
