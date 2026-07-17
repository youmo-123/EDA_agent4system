#!/usr/bin/env python3
"""a3 backend: Icarus 门级功能预检（可选）。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import now_iso
from scripts.common.atomic_io import write_json_atomic
from scripts.common.command import run_command
from scripts.common.script_cli import ScriptResult, run_script


def _locate() -> tuple[str | None, str | None]:
    iv = os.environ.get("DOORAGENT_ICARUS_IVERILOG_BIN") or shutil.which("iverilog")
    vvp = os.environ.get("DOORAGENT_ICARUS_VVP_BIN") or shutil.which("vvp")
    return iv, vvp


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    netlist = Path(params.get("netlist_ref") or "")
    tb = params.get("tb_ref")
    if not netlist.exists() or not tb:
        return ScriptResult(status="unsupported", error_code="CAPABILITY_UNAVAILABLE",
                            error={"message": "netlist_ref and tb_ref required"})
    iv, vvp = _locate()
    if not iv or not vvp:
        return ScriptResult(status="unsupported", error_code="CAPABILITY_UNAVAILABLE",
                            error={"message": "iverilog/vvp not found"})
    vvp_file = work_dir / "run.vvp"
    compile_r = run_command([iv, "-o", str(vvp_file), str(netlist), tb],
                             cwd=work_dir, timeout_s=300)
    (work_dir / "iverilog.log").write_text(compile_r.stdout + "\n" + compile_r.stderr,
                                            encoding="utf-8")
    if compile_r.exit_code != 0 or not vvp_file.exists():
        write_json_atomic(work_dir / "precheck-result.json", {
            "status": "failed", "log_ref": "iverilog.log", "created_at": now_iso(),
        })
        return ScriptResult(status="failed", error_code="A3_EQUIVALENCE_FAILED",
                            output_artifact_refs=["iverilog.log", "precheck-result.json"],
                            error={"message": "iverilog compile failed"})
    run_r = run_command([vvp, str(vvp_file)], cwd=work_dir, timeout_s=300)
    (work_dir / "vvp.log").write_text(run_r.stdout + "\n" + run_r.stderr, encoding="utf-8")
    status = "passed" if run_r.exit_code == 0 else "failed"
    write_json_atomic(work_dir / "precheck-result.json", {
        "status": status, "log_ref": "vvp.log", "created_at": now_iso(),
    })
    return ScriptResult(
        status="completed" if status == "passed" else "failed",
        output_artifact_refs=["precheck-result.json", "iverilog.log", "vvp.log"],
        raw_metrics={"status": status},
        tool_versions={"iverilog": _iverilog_version(iv)},
    )


def _iverilog_version(iv: str) -> str:
    r = run_command([iv, "-V"], timeout_s=10)
    return (r.stdout or "").splitlines()[0] if r.exit_code == 0 else "unknown"


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_icarus",
        description="Icarus gate-level pre-check",
        handler=handle,
    ))
