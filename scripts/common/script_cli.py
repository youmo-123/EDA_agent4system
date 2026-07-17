"""script_cli：所有自写 script 的统一 CLI 骨架。

约束（方案 14.5.1）：
- --request-json / --result-json / --work-dir / --timeout-s
- stdout 只输出简短进度
- 退出码：
    0 = completed
    2 = invalid request
    3 = tool unavailable
    4 = tool failed
    5 = output invalid
    124 = timeout
    130 = cancelled
- result.json 必须包含：
    status / error_code / tool_versions / command_refs /
    output_artifact_refs / diagnostics / wall_time_s
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from scripts.common.atomic_io import write_json_atomic


EXIT_COMPLETED = 0
EXIT_INVALID_REQUEST = 2
EXIT_TOOL_UNAVAILABLE = 3
EXIT_TOOL_FAILED = 4
EXIT_OUTPUT_INVALID = 5
EXIT_TIMEOUT = 124
EXIT_CANCELLED = 130


@dataclass
class ScriptResult:
    status: str = "completed"   # completed | partial | failed | timeout | cancelled | unsupported | unavailable
    error_code: str | None = None
    tool_versions: dict[str, Any] = field(default_factory=dict)
    command_refs: list[str] = field(default_factory=list)
    output_artifact_refs: list[str] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    wall_time_s: float = 0.0
    raw_metrics: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error_code": self.error_code,
            "tool_versions": self.tool_versions,
            "command_refs": self.command_refs,
            "output_artifact_refs": self.output_artifact_refs,
            "diagnostics": self.diagnostics,
            "wall_time_s": self.wall_time_s,
            "raw_metrics": self.raw_metrics,
            "error": self.error,
        }


HandlerT = Callable[[dict[str, Any], Path], ScriptResult]


def build_parser(prog: str, description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=description)
    p.add_argument("--request-json", help="path to input request JSON")
    p.add_argument("--result-json", help="path to output result JSON")
    p.add_argument("--work-dir", help="scratch directory (relative or absolute)")
    p.add_argument("--timeout-s", type=int, default=600)
    p.add_argument("--self-check", action="store_true",
                   help="minimal self-check without executing real work")
    return p


def run_script(*, prog: str, description: str, handler: HandlerT,
               argv: list[str] | None = None) -> int:
    """通用 script main：解析参数、执行 handler、按契约写 result.json。"""
    parser = build_parser(prog, description)
    args = parser.parse_args(argv)

    if args.self_check:
        # health check 走最小路径
        result = ScriptResult(status="completed",
                              raw_metrics={"self_check": True})
        print(f"[{prog}] self-check ok")
        if args.result_json:
            write_json_atomic(Path(args.result_json), result.to_dict())
        return EXIT_COMPLETED

    if not args.request_json or not args.result_json or not args.work_dir:
        print(f"[{prog}] error: --request-json / --result-json / --work-dir required",
              file=sys.stderr)
        return EXIT_INVALID_REQUEST

    request_path = Path(args.request_json)
    result_path = Path(args.result_json)
    work_dir = Path(args.work_dir)
    if not request_path.exists():
        print(f"[{prog}] error: request not found: {request_path}", file=sys.stderr)
        return EXIT_INVALID_REQUEST
    work_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _write_error(result_path, "INVALID_REQUEST", f"bad JSON: {exc}", 0.0)
        return EXIT_INVALID_REQUEST

    try:
        res = handler(request, work_dir)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        elapsed = time.time() - t0
        _write_error(result_path, "TOOL_CRASHED",
                     f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1200:]}",
                     elapsed)
        return EXIT_TOOL_FAILED

    res.wall_time_s = res.wall_time_s or (time.time() - t0)
    write_json_atomic(result_path, res.to_dict())
    return _status_to_exit(res.status)


def _write_error(result_path: Path, code: str, message: str, elapsed: float) -> None:
    r = ScriptResult(
        status="failed",
        error_code=code,
        error={"message": message},
        wall_time_s=elapsed,
    )
    write_json_atomic(result_path, r.to_dict())


def _status_to_exit(status: str) -> int:
    mapping = {
        "completed": EXIT_COMPLETED,
        "partial": EXIT_COMPLETED,
        "failed": EXIT_TOOL_FAILED,
        "timeout": EXIT_TIMEOUT,
        "cancelled": EXIT_CANCELLED,
        "unsupported": EXIT_TOOL_UNAVAILABLE,
        "unavailable": EXIT_TOOL_UNAVAILABLE,
    }
    return mapping.get(status, EXIT_TOOL_FAILED)
