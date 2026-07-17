#!/usr/bin/env python3
"""a3 backend: OpenSTA 静态时序分析。"""
from __future__ import annotations

import os
import re
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


def _locate_sta() -> str | None:
    p = os.environ.get("DOORAGENT_OPENSTA_BIN") or shutil.which("sta")
    return p if p and (Path(p).exists() or shutil.which(p)) else None


TCL_TEMPLATE = """\
read_liberty {library}
read_verilog {netlist}
link_design {top}
read_sdc {sdc}
report_checks -digits 3 -path_delay max
report_worst_slack -digits 3
exit
"""


_SLACK_RE = re.compile(r"worst\s+slack\s*[:=]?\s*(-?\d+\.?\d*)", re.IGNORECASE)
_ARRIVAL_RE = re.compile(r"data\s+arrival\s+time\s+(-?\d+\.?\d*)", re.IGNORECASE)


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    netlist = Path(params.get("netlist_ref") or "")
    sdc = Path(params.get("sdc_ref") or "")
    library = Path(params.get("technology_library_ref") or "")
    top = params.get("top", "top")
    timeout_s = int(params.get("timeout_s", 600))
    if not (netlist.exists() and library.exists() and sdc.exists()):
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "netlist_ref/sdc_ref/technology_library_ref required"})
    sta = _locate_sta()
    if not sta:
        return ScriptResult(status="unavailable", error_code="CAPABILITY_UNAVAILABLE",
                            error={"message": "OpenSTA not found; set DOORAGENT_OPENSTA_BIN"})
    tcl = work_dir / "sta.tcl"
    tcl.write_text(TCL_TEMPLATE.format(
        library=library, netlist=netlist, sdc=sdc, top=top,
    ), encoding="utf-8")
    r = run_command([sta, "-no_init", "-no_splash", "-f", str(tcl)],
                    cwd=work_dir, timeout_s=timeout_s)
    (work_dir / "sta.stdout.log").write_text(r.stdout, encoding="utf-8")
    (work_dir / "sta.stderr.log").write_text(r.stderr, encoding="utf-8")

    slack = None
    arrival = None
    m = _SLACK_RE.search(r.stdout)
    if m:
        try:
            slack = float(m.group(1))
        except ValueError:
            slack = None
    m2 = _ARRIVAL_RE.search(r.stdout)
    if m2:
        try:
            arrival = float(m2.group(1))
        except ValueError:
            arrival = None

    timing_result = {
        "arrival": arrival,
        "slack": slack,
        "critical_path": [],
        "backend": "opensta",
        "raw_report_ref": "sta.stdout.log",
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "timing-result.json", timing_result)
    status = "completed" if r.exit_code == 0 else "failed"
    return ScriptResult(
        status=status,
        error_code=None if status == "completed" else "A3_TIMING_ESTIMATION_FAILED",
        output_artifact_refs=["timing-result.json", "sta.stdout.log", "sta.stderr.log", "sta.tcl"],
        raw_metrics={"slack": slack, "arrival": arrival},
        tool_versions={"opensta": _sta_version(sta)},
        command_refs=[" ".join(r.command)],
    )


def _sta_version(sta: str) -> str:
    r = run_command([sta, "-version"], timeout_s=10)
    return (r.stdout or r.stderr or "").strip().splitlines()[0] if (r.exit_code in (0, 1)) else "unknown"


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a3_opensta",
        description="OpenSTA timing analysis",
        handler=handle,
    ))
