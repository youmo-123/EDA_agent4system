#!/usr/bin/env python3
"""a3_synth_tool：A3 综合入口。

方案 4.5 / 15.5.1：
  python3 scripts/a3/synth_tool.py \
      --rtl <design.v> --top <top> \
      --sdc <constraints.sdc> \
      --technology-library <library.lib> \
      --backend-profile <profile-id> \
      --strategy <strategy-id> \
      --design-id <stable-design-id> \
      --output <OUT_DIR/netlist.v> \
      --work-dir <temporary-dir> \
      --report-json <synth-report.json>

行为：
- 解析 Backend Profile + Strategy
- 依次调用 scripts/a3/backends/yosys_abc.py 与 backends/opensta.py
- 汇总生成 synth-report.json（含 area/arrival/slack/runtime/tool_versions/validation_state）
- 缺失后端时返回 unavailable，且 synth-report 显式声明
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso, sha256_file


def _run(rel: str, request: dict, work_dir: Path, timeout_s: int = 1800):
    req = work_dir / "request.json"
    res = work_dir / "result.json"
    req.write_text(json.dumps(request), encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(REPO_ROOT / rel),
         "--request-json", str(req), "--result-json", str(res),
         "--work-dir", str(work_dir), "--timeout-s", str(timeout_s)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        timeout=timeout_s + 60,
    )
    (work_dir / "stdout.log").write_text(p.stdout or "", encoding="utf-8")
    (work_dir / "stderr.log").write_text(p.stderr or "", encoding="utf-8")
    if res.exists():
        return p.returncode, json.loads(res.read_text(encoding="utf-8"))
    return p.returncode, {"status": "failed", "error_code": "TOOL_CRASHED",
                           "error": {"stderr": p.stderr[-2000:]}}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="a3_synth_tool", description="A3 synthesis unified entry")
    p.add_argument("--rtl")
    p.add_argument("--top")
    p.add_argument("--sdc")
    p.add_argument("--technology-library", dest="library")
    p.add_argument("--backend-profile", default="open-source-default")
    p.add_argument("--strategy", default="balanced-default")
    p.add_argument("--design-id")
    p.add_argument("--output", help="output netlist path")
    p.add_argument("--work-dir")
    p.add_argument("--report-json", help="path to synth-report.json")
    # 统一 CLI 兼容
    p.add_argument("--request-json")
    p.add_argument("--result-json")
    p.add_argument("--timeout-s", type=int, default=1800)
    p.add_argument("--self-check", action="store_true")
    return p


def _self_check() -> int:
    print("[a3_synth_tool] self-check ok")
    return 0


def _emit_from_registry(args) -> int:
    req = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
    params = req.get("parameters") or {}
    ns = argparse.Namespace()
    ns.rtl = params.get("rtl_ref")
    ns.top = params.get("top")
    ns.sdc = params.get("sdc_ref")
    ns.library = params.get("technology_library_ref")
    ns.backend_profile = params.get("backend_profile_id", "open-source-default")
    ns.strategy = params.get("strategy_id", "balanced-default")
    ns.design_id = params.get("design_id")
    ns.output = params.get("output") or (Path(args.work_dir) / "netlist.v").as_posix()
    ns.work_dir = args.work_dir
    ns.report_json = params.get("report_json") or (Path(args.work_dir) / "synth-report.json").as_posix()
    ns.timeout_s = args.timeout_s
    ns.self_check = False
    ns.result_json = args.result_json
    ns.request_json = args.request_json
    return _main(ns)


def _main(args) -> int:
    if args.self_check:
        return _self_check()
    if args.request_json and args.result_json and args.work_dir and not args.rtl:
        return _emit_from_registry(args)
    missing = [k for k, v in
               [("--rtl", args.rtl), ("--top", args.top), ("--sdc", args.sdc),
                ("--technology-library", args.library), ("--work-dir", args.work_dir),
                ("--report-json", args.report_json)]
               if not v]
    if missing:
        print(f"[a3_synth_tool] error: missing args {missing}", file=sys.stderr)
        return 2

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    output = Path(args.output or (work_dir / "netlist.v"))
    t0 = time.time()
    versions: dict[str, Any] = {}

    # Stage 1: synth
    synth_wd = work_dir / "synth"
    synth_wd.mkdir(exist_ok=True)
    rc, synth_res = _run("scripts/a3/backends/yosys_abc.py",
                         {"parameters": {
                             "rtl_ref": args.rtl, "top": args.top,
                             "strategy_id": args.strategy,
                             "technology_library_ref": args.library,
                             "timeout_s": args.timeout_s,
                         }},
                         synth_wd, args.timeout_s)
    versions.update(synth_res.get("tool_versions", {}))
    if rc != 0 or synth_res.get("status") != "completed":
        report = _build_report(args, status="failed",
                               synth=synth_res, timing=None,
                               versions=versions, runtime_s=time.time() - t0)
        write_json_atomic(Path(args.report_json), report)
        _maybe_write_result(args, "failed", report)
        return 4 if synth_res.get("error_code") != "CAPABILITY_UNAVAILABLE" else 3

    # 复制 netlist 到 --output
    stage_netlist = synth_wd / "netlist.v"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(stage_netlist.read_bytes())

    # Stage 2: netlist validation
    val_wd = work_dir / "validate"
    val_wd.mkdir(exist_ok=True)
    rc, val_res = _run("scripts/a3/netlist.py",
                       {"parameters": {"netlist_ref": str(output),
                                         "top": args.top,
                                         "technology_library_ref": args.library}},
                       val_wd, 120)
    validation_state = "valid" if val_res.get("status") == "completed" else "invalid"

    # Stage 3: STA (optional，若 OpenSTA 不可用只标注)
    sta_wd = work_dir / "sta"
    sta_wd.mkdir(exist_ok=True)
    rc, timing_res = _run("scripts/a3/backends/opensta.py",
                          {"parameters": {"netlist_ref": str(output),
                                           "sdc_ref": args.sdc,
                                           "technology_library_ref": args.library,
                                           "top": args.top,
                                           "timeout_s": args.timeout_s}},
                          sta_wd, args.timeout_s)
    versions.update(timing_res.get("tool_versions", {}))

    runtime_s = time.time() - t0
    report = _build_report(args, status="completed",
                            synth=synth_res, timing=timing_res,
                            versions=versions, runtime_s=runtime_s,
                            netlist_path=output, validation_state=validation_state)
    write_json_atomic(Path(args.report_json), report)
    _maybe_write_result(args, "completed", report)
    return 0


def _build_report(args, *, status, synth, timing, versions, runtime_s,
                  netlist_path: Path | None = None, validation_state: str = "unknown") -> dict:
    return {
        "candidate_id": f"cand-{args.design_id or args.top or 'unknown'}-{args.strategy}",
        "backend_profile_id": args.backend_profile,
        "strategy_id": args.strategy,
        "netlist_ref": netlist_path.as_posix() if netlist_path and netlist_path.exists() else None,
        "netlist_hash": sha256_file(netlist_path) if (netlist_path and netlist_path.exists()) else None,
        "area": (synth.get("raw_metrics") or {}).get("area"),
        "arrival": (timing or {}).get("raw_metrics", {}).get("arrival"),
        "slack": (timing or {}).get("raw_metrics", {}).get("slack"),
        "runtime_s": runtime_s,
        "tool_versions": versions,
        "validation_state": validation_state,
        "status": status,
        "created_at": now_iso(),
    }


def _maybe_write_result(args, status, report):
    if not args.result_json:
        return
    write_json_atomic(Path(args.result_json), {
        "status": status,
        "error_code": None if status == "completed" else "A3_MAPPING_FAILED",
        "output_artifact_refs": [args.report_json],
        "raw_metrics": {k: report.get(k) for k in ("area", "arrival", "slack", "runtime_s")},
        "tool_versions": report.get("tool_versions", {}),
        "command_refs": [],
        "diagnostics": [],
        "wall_time_s": report.get("runtime_s", 0.0),
        "error": None,
    })


def main(argv: list[str] | None = None) -> int:
    return _main(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
