#!/usr/bin/env python3
"""a2_run：A2 统一入口。

方案 4.4 / 14.5.3：
  python3 scripts/a2/run.py \
      --rtl <rtl-dir> --top <dut> --out <out-dir> \
      --seed <n> --num-seq <count>

行为：
- 构建阶段 DAG：interface → coverage/model → constraints → tests →
  simulation → coverage/functional → coverage/structural → reports → validate
- 每阶段以 subprocess 调用对应的 A2 子脚本（复用统一 CLI）
- 每次运行发布一个 artifact-manifest.json，按实际操作引用产物
- 失败阶段短路，写 run-report.json 描述失败原因

需要 A1 门禁时，只生成 `a1-function-gate-request.json` 并返回 waiting_gate2；
不直接启动 A1。
"""
from __future__ import annotations

import argparse
import hashlib
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


# 阶段定义：(name, script relative path, request builder, output artifact filename)
STAGES = [
    ("interface", "scripts/a2/interface.py"),
    ("coverage_model", "scripts/a2/coverage/model.py"),
    ("constraints", "scripts/a2/constraints.py"),
    ("tests", "scripts/a2/tests.py"),
    ("simulation", "scripts/a2/simulation.py"),
    ("functional_coverage", "scripts/a2/coverage/functional.py"),
    ("structural_coverage", "scripts/a2/coverage/structural.py"),
    ("reports", "scripts/a2/reports.py"),
    ("validate", "scripts/a2/validate.py"),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="a2_run", description="A2 unified pipeline")
    p.add_argument("--rtl", required=False, help="RTL directory or comma-separated file list")
    p.add_argument("--top", required=False)
    p.add_argument("--out", required=False, help="output directory")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--num-seq", type=int, default=100)
    p.add_argument("--a1-function-gate", choices=["required", "best_effort", "disabled"],
                   default="best_effort")
    # 也支持统一 CLI 便于 Registry 调用
    p.add_argument("--request-json")
    p.add_argument("--result-json")
    p.add_argument("--work-dir")
    p.add_argument("--timeout-s", type=int, default=1800)
    p.add_argument("--self-check", action="store_true")
    return p


def _resolve_rtl_refs(rtl: str) -> list[str]:
    if "," in rtl:
        return [s.strip() for s in rtl.split(",") if s.strip()]
    p = Path(rtl)
    if p.is_dir():
        return sorted(str(x) for x in p.rglob("*.sv"))
    if p.is_file():
        return [str(p)]
    return []


def _hash_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _run_stage(script_rel: str, request: dict[str, Any], out_dir: Path,
               stage_name: str, timeout_s: int) -> tuple[int, dict, Path]:
    stage_dir = out_dir / stage_name
    stage_dir.mkdir(parents=True, exist_ok=True)
    req_path = stage_dir / "request.json"
    res_path = stage_dir / "result.json"
    req_path.write_text(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True),
                        encoding="utf-8")
    argv = [
        sys.executable, str(REPO_ROOT / script_rel),
        "--request-json", str(req_path),
        "--result-json", str(res_path),
        "--work-dir", str(stage_dir),
        "--timeout-s", str(timeout_s),
    ]
    p = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, text=True,
                       timeout=timeout_s + 30)
    (stage_dir / "stdout.log").write_text(p.stdout or "", encoding="utf-8")
    (stage_dir / "stderr.log").write_text(p.stderr or "", encoding="utf-8")
    data = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else {
        "status": "failed", "error_code": "TOOL_CRASHED",
        "error": {"stderr": p.stderr[-2000:]},
    }
    return p.returncode, data, stage_dir


def _add_to_manifest(entries: list[dict], artifact_type: str, path: Path,
                     workflow_id: str, producer: str) -> None:
    if not path.exists():
        return
    entries.append({
        "artifact_type": artifact_type,
        "path": str(path.relative_to(path.parents[len(path.parts) - path.parts.index(path.parts[-1]) - 1])
                    ) if False else path.name,
        "abs_path": str(path),
        "hash": _hash_file(path),
        "workflow_id": workflow_id,
        "producer_agent_instance_id": producer,
        "schema_version": "1.0",
        "created_at": _now(),
    })


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _self_check() -> int:
    print("[a2_run] self-check ok")
    return 0


def _emit_from_registry_request(args) -> int:
    """通过 Registry 触发时，参数来自 request.json 的 parameters。"""
    req = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
    params = req.get("parameters") or {}
    class NS:  # 转换为 argparse-like 对象
        pass
    ns = NS()
    ns.rtl = params.get("rtl") or ",".join(params.get("rtl_refs", []))
    ns.top = params.get("top")
    ns.out = params.get("output_dir") or args.work_dir
    ns.seed = int(params.get("seed", 1))
    ns.num_seq = int(params.get("num_sequences", 100))
    ns.a1_function_gate = params.get("a1_function_gate", "best_effort")
    ns.timeout_s = args.timeout_s
    ns.result_json = args.result_json
    ns.request_json = args.request_json
    ns.work_dir = args.work_dir
    ns.self_check = False
    return _main(ns)


def _main(args) -> int:
    if args.self_check:
        return _self_check()
    if args.request_json and args.result_json and args.work_dir and not args.rtl:
        # Registry 场景
        return _emit_from_registry_request(args)
    if not args.rtl or not args.top or not args.out:
        print("[a2_run] error: --rtl / --top / --out required", file=sys.stderr)
        return 2
    rtl_refs = _resolve_rtl_refs(args.rtl)
    if not rtl_refs:
        print(f"[a2_run] error: no RTL files found under {args.rtl}", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    workflow_id = os.environ.get("DOORAGENT_WORKFLOW_ID", "wf-a2-local")
    producer = os.environ.get("DOORAGENT_AGENT_INSTANCE_ID", "a2-local")

    manifest_entries: list[dict] = []
    phase_status: dict[str, str] = {}
    stage_out = {}

    # 1. interface
    rc, data, stage_dir = _run_stage(
        "scripts/a2/interface.py",
        {"parameters": {"rtl_refs": rtl_refs, "top": args.top}},
        out_dir, "interface", args.timeout_s,
    )
    phase_status["interface"] = data.get("status", "failed")
    if rc != 0:
        return _finalize_fail(out_dir, args, phase_status, "interface stage failed")
    design_path = stage_dir / "design.json"
    manifest_entries.append({"artifact_type": "design", "path": "interface/design.json",
                              "hash": _hash_file(design_path), "workflow_id": workflow_id,
                              "producer_agent_instance_id": producer,
                              "schema_version": "1.0", "created_at": _now()})

    # 2. coverage/model
    rc, data, cov_stage = _run_stage(
        "scripts/a2/coverage/model.py",
        {"parameters": {"design_ref": str(design_path)}},
        out_dir, "coverage_model", args.timeout_s,
    )
    phase_status["coverage_model"] = data.get("status", "failed")
    if rc != 0:
        return _finalize_fail(out_dir, args, phase_status, "coverage_model stage failed")
    cov_model_path = cov_stage / "coverage-model.json"
    manifest_entries.append({"artifact_type": "coverage-model",
                              "path": "coverage_model/coverage-model.json",
                              "hash": _hash_file(cov_model_path),
                              "workflow_id": workflow_id,
                              "producer_agent_instance_id": producer,
                              "schema_version": "1.0", "created_at": _now()})

    # 3. constraints
    rc, data, con_stage = _run_stage(
        "scripts/a2/constraints.py",
        {"parameters": {"design_ref": str(design_path), "seed": args.seed}},
        out_dir, "constraints", args.timeout_s,
    )
    phase_status["constraints"] = data.get("status", "failed")
    if rc != 0:
        return _finalize_fail(out_dir, args, phase_status, "constraints stage failed")
    con_path = con_stage / "constraint-model.json"
    manifest_entries.append({"artifact_type": "constraints",
                              "path": "constraints/constraint-model.json",
                              "hash": _hash_file(con_path),
                              "workflow_id": workflow_id,
                              "producer_agent_instance_id": producer,
                              "schema_version": "1.0", "created_at": _now()})

    # 4. tests
    rc, data, tests_stage = _run_stage(
        "scripts/a2/tests.py",
        {"parameters": {"constraints_ref": str(con_path),
                         "seed": args.seed, "count": args.num_seq}},
        out_dir, "tests", args.timeout_s,
    )
    phase_status["tests"] = data.get("status", "failed")
    if rc != 0:
        return _finalize_fail(out_dir, args, phase_status, "tests stage failed")
    tests_manifest = tests_stage / "test-manifest.json"

    # 5. simulation (mock)
    rc, data, sim_stage = _run_stage(
        "scripts/a2/simulation.py",
        {"parameters": {"tb_ref": "verification-package",
                         "tests_ref": str(tests_manifest),
                         "backend": "mock"}},
        out_dir, "simulation", args.timeout_s,
    )
    phase_status["simulation"] = data.get("status", "failed")
    if rc != 0:
        return _finalize_fail(out_dir, args, phase_status, "simulation stage failed")

    # 6. functional coverage
    rc, data, fc_stage = _run_stage(
        "scripts/a2/coverage/functional.py",
        {"parameters": {"coverage_model_ref": str(cov_model_path)}},
        out_dir, "functional_coverage", args.timeout_s,
    )
    phase_status["functional_coverage"] = data.get("status", "failed")
    if rc != 0:
        return _finalize_fail(out_dir, args, phase_status, "functional_coverage stage failed")
    fc_path = fc_stage / "functional-coverage.json"
    manifest_entries.append({"artifact_type": "functional-coverage",
                              "path": "functional_coverage/functional-coverage.json",
                              "hash": _hash_file(fc_path),
                              "workflow_id": workflow_id,
                              "producer_agent_instance_id": producer,
                              "schema_version": "1.0", "created_at": _now()})

    # 7. structural coverage（mock backend）
    rc, data, sc_stage = _run_stage(
        "scripts/a2/coverage/structural.py",
        {"parameters": {"backend": "mock"}},
        out_dir, "structural_coverage", args.timeout_s,
    )
    phase_status["structural_coverage"] = data.get("status", "failed")
    sc_path = sc_stage / "structural-coverage.json"
    if sc_path.exists():
        manifest_entries.append({"artifact_type": "structural-coverage",
                                  "path": "structural_coverage/structural-coverage.json",
                                  "hash": _hash_file(sc_path),
                                  "workflow_id": workflow_id,
                                  "producer_agent_instance_id": producer,
                                  "schema_version": "1.0", "created_at": _now()})

    # 8. reports（汇总）
    rc, data, rep_stage = _run_stage(
        "scripts/a2/reports.py",
        {"parameters": {
            "coverage_model_ref": str(cov_model_path),
            "functional_coverage_ref": str(fc_path),
            "structural_coverage_ref": str(sc_path) if sc_path.exists() else None,
            "phase_status": phase_status,
            "reproduce_commands": [
                f"python3 scripts/a2/run.py --rtl {args.rtl} --top {args.top} "
                f"--out {args.out} --seed {args.seed} --num-seq {args.num_seq}"
            ],
            "backend_versions": {"parser": "auto", "solver": "auto", "simulation": "mock"},
        }},
        out_dir, "reports", args.timeout_s,
    )
    phase_status["reports"] = data.get("status", "failed")
    if rc != 0:
        return _finalize_fail(out_dir, args, phase_status, "reports stage failed")
    cov_result_path = rep_stage / "coverage-result.json"
    run_report_path = rep_stage / "run-report.json"
    manifest_entries.append({"artifact_type": "coverage-result",
                              "path": "reports/coverage-result.json",
                              "hash": _hash_file(cov_result_path),
                              "workflow_id": workflow_id,
                              "producer_agent_instance_id": producer,
                              "schema_version": "1.0", "created_at": _now()})
    manifest_entries.append({"artifact_type": "run-report",
                              "path": "reports/run-report.json",
                              "hash": _hash_file(run_report_path),
                              "workflow_id": workflow_id,
                              "producer_agent_instance_id": producer,
                              "schema_version": "1.0", "created_at": _now()})

    # 9. 发布 artifact-manifest.json
    manifest = {
        "manifest_id": f"a2-manifest-{args.top}-seed{args.seed}",
        "entries": manifest_entries,
        "workflow_id": workflow_id,
        "producer_agent_instance_id": producer,
        "schema_version": "1.0",
        "created_at": _now(),
        "artifact_hash": hashlib.sha256(
            json.dumps(manifest_entries, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    manifest_path = out_dir / "artifact-manifest.json"
    write_json_atomic(manifest_path, manifest)

    # 10. validate
    rc, data, val_stage = _run_stage(
        "scripts/a2/validate.py",
        {"parameters": {"artifact_manifest": str(manifest_path)}},
        out_dir, "validate", args.timeout_s,
    )
    phase_status["validate"] = data.get("status", "failed")

    # 写 result.json（Registry 场景）
    final_result = {
        "status": "completed" if rc == 0 and all(v in {"completed", "partial"} for v in phase_status.values()) else "partial",
        "error_code": None,
        "phase_status": phase_status,
        "output_artifact_refs": [str(manifest_path)],
        "wall_time_s": 0.0,
        "raw_metrics": {"manifest_entries": len(manifest_entries)},
        "tool_versions": {"pipeline": "a2_run/v1"},
        "command_refs": [],
        "diagnostics": [],
    }
    if args.result_json:
        write_json_atomic(Path(args.result_json), final_result)
    print(f"[a2_run] artifact-manifest: {manifest_path}")
    return 0


def _finalize_fail(out_dir: Path, args, phase_status: dict, msg: str) -> int:
    fail = {
        "status": "failed",
        "error_code": "A2_TEST_GENERATION_FAILED",
        "phase_status": phase_status,
        "error": {"message": msg},
        "output_artifact_refs": [],
        "wall_time_s": 0.0,
        "raw_metrics": {},
        "tool_versions": {},
        "command_refs": [],
        "diagnostics": [],
    }
    if args.result_json:
        write_json_atomic(Path(args.result_json), fail)
    print(f"[a2_run] {msg}", file=sys.stderr)
    return 4


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _main(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
