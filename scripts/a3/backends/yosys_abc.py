#!/usr/bin/env python3
"""a3 backend: Yosys + ABC 综合调用。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.artifact_io import now_iso, sha256_file
from scripts.common.atomic_io import write_json_atomic
from scripts.common.command import run_command
from scripts.common.script_cli import ScriptResult, run_script


def _locate_yosys() -> str | None:
    p = os.environ.get("DOORAGENT_YOSYS_BIN") or shutil.which("yosys")
    if not p:
        return None
    return p if (Path(p).exists() or shutil.which(p)) else None


def _load_strategies() -> dict[str, dict]:
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib
    cfg = REPO_ROOT / "configs" / "algorithms" / "a3-strategies.toml"
    if not cfg.exists():
        return {}
    return {s["strategy_id"]: s for s in tomllib.loads(cfg.read_text(encoding="utf-8")).get("strategies", [])}


def _yosys_script(rtl: Path, top: str, library: Path, strategy: dict, netlist_out: Path) -> str:
    prep = strategy.get("parameters", {}).get("yosys_prep",
                                              "hierarchy -auto-top; proc; flatten; opt; memory; opt")
    abc_script = strategy.get("parameters", {}).get("abc_script", "compress2rs; dch; if -K 6")
    return (
        f"read_verilog {rtl}\n"
        f"{prep}\n"
        f"techmap\n"
        f'abc -liberty {library} -script "+{abc_script}"\n'
        f"opt_clean -purge\n"
        f"hierarchy -top {top}\n"
        f"write_verilog {netlist_out}\n"
    )


def _yosys_version(yosys: str) -> str:
    r = run_command([yosys, "-V"], timeout_s=10)
    if r.exit_code == 0 and r.stdout:
        return r.stdout.strip().splitlines()[0]
    return "unknown"


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    rtl = Path(params.get("rtl_ref") or "")
    top = params.get("top", "")
    strategy_id = params.get("strategy_id", "balanced-default")
    library = Path(params.get("technology_library_ref") or "")
    timeout_s = int(params.get("timeout_s", 1200))
    if not rtl.exists() or not top:
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "rtl_ref / top required"})
    if not library.exists():
        return ScriptResult(status="unavailable", error_code="CAPABILITY_UNAVAILABLE",
                            error={"message": f"technology_library missing: {library}"})
    yosys = _locate_yosys()
    if not yosys:
        return ScriptResult(status="unavailable", error_code="CAPABILITY_UNAVAILABLE",
                            error={"message": "yosys not found; set DOORAGENT_YOSYS_BIN"})
    strategies = _load_strategies()
    strategy = strategies.get(strategy_id)
    if not strategy:
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": f"unknown strategy_id: {strategy_id}"})

    netlist = work_dir / "netlist.v"
    ys_script = work_dir / "run.ys"
    ys_script.write_text(_yosys_script(rtl, top, library, strategy, netlist), encoding="utf-8")

    r = run_command([yosys, "-s", str(ys_script)], cwd=work_dir, timeout_s=timeout_s)
    (work_dir / "yosys.stdout.log").write_text(r.stdout, encoding="utf-8")
    (work_dir / "yosys.stderr.log").write_text(r.stderr, encoding="utf-8")

    write_json_atomic(work_dir / "synthesis-backend-run.json", {
        "run_id": f"synth-{strategy_id}",
        "backend": "yosys+abc",
        "commands": [" ".join(r.command)],
        "exit_code": r.exit_code,
        "stdout_ref": "yosys.stdout.log",
        "stderr_ref": "yosys.stderr.log",
        "created_at": now_iso(),
    })

    if r.exit_code != 0 or not netlist.exists() or netlist.stat().st_size == 0:
        return ScriptResult(
            status="failed", error_code="A3_MAPPING_FAILED",
            output_artifact_refs=["synthesis-backend-run.json", "run.ys",
                                  "yosys.stdout.log", "yosys.stderr.log"],
            error={"message": "yosys exited non-zero or empty netlist",
                   "exit_code": r.exit_code},
        )
    return ScriptResult(
        status="completed",
        output_artifact_refs=["netlist.v", "synthesis-backend-run.json", "run.ys"],
        raw_metrics={"netlist_bytes": netlist.stat().st_size,
                     "netlist_hash": sha256_file(netlist)},
        tool_versions={"yosys": _yosys_version(yosys)},
        command_refs=[" ".join(r.command)],
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_yosys_abc",
        description="Synthesize with Yosys + ABC using a strategy",
        handler=handle,
    ))
