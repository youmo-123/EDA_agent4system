#!/usr/bin/env python3
"""a3_equivalence_check：优先 Yosys 等价检查；无法证明返回 inconclusive。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import now_iso
from scripts.common.atomic_io import write_json_atomic
from scripts.common.command import run_command
from scripts.common.script_cli import ScriptResult, run_script


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    orig = Path(params.get("original_rtl_ref") or "")
    netlist = Path(params.get("netlist_ref") or "")
    top = params.get("top", "top")
    if not (orig.exists() and netlist.exists()):
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "original_rtl_ref and netlist_ref required"})
    yosys = os.environ.get("DOORAGENT_YOSYS_BIN") or shutil.which("yosys")
    if not yosys:
        # 无 yosys：返回 inconclusive
        eq = {"status": "inconclusive", "method": "yosys-missing",
              "evidence_ref": None, "created_at": now_iso()}
        write_json_atomic(work_dir / "equivalence-result.json", eq)
        return ScriptResult(status="unsupported",
                            error_code="CAPABILITY_UNAVAILABLE",
                            output_artifact_refs=["equivalence-result.json"],
                            raw_metrics=eq)
    script = work_dir / "eq.ys"
    script.write_text(
        f"read_verilog -sv {orig}\n"
        f"prep -top {top}\n"
        f"design -save gold\n"
        f"read_verilog {netlist}\n"
        f"prep -top {top}\n"
        f"design -save gate\n"
        f"design -copy-from gold -as gold {top}\n"
        f"design -copy-from gate -as gate {top}\n"
        f"equiv_make gold gate equiv\n"
        f"hierarchy -top equiv\n"
        f"equiv_simple\n"
        f"equiv_status -assert\n",
        encoding="utf-8",
    )
    r = run_command([yosys, "-s", str(script)], cwd=work_dir, timeout_s=900)
    (work_dir / "yosys-eq.log").write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
    status = "equivalent" if r.exit_code == 0 else "inconclusive"
    eq = {"status": status, "method": "yosys-equiv_simple",
          "evidence_ref": "yosys-eq.log", "created_at": now_iso()}
    write_json_atomic(work_dir / "equivalence-result.json", eq)
    return ScriptResult(
        status="completed",
        output_artifact_refs=["equivalence-result.json", "yosys-eq.log", "eq.ys"],
        raw_metrics=eq,
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_equivalence_check",
        description="Yosys-based equivalence check",
        handler=handle,
    ))
