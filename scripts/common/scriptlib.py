from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable


def atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(partial, path)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def common_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--timeout-s", type=int, default=600)
    return parser


def run_common(description: str, handler: Callable[[dict[str, Any], Path], dict[str, Any]]) -> int:
    args = common_parser(description).parse_args()
    start = time.monotonic()
    try:
        request = load_json(Path(args.request_json))
        work_dir = Path(args.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        result = handler(request, work_dir)
        result.setdefault("status", "completed")
        result.setdefault("error_code", None)
        result.setdefault("tool_versions", {})
        result.setdefault("command_refs", [])
        result.setdefault("output_artifact_refs", [])
        result.setdefault("diagnostics", [])
        result["wall_time_s"] = time.monotonic() - start
        atomic_write(Path(args.result_json), result)
        return 0 if result["status"] == "completed" else 4
    except ValueError as exc:
        atomic_write(Path(args.result_json), {"status": "failed", "error_code": "INVALID_REQUEST", "message": str(exc), "wall_time_s": time.monotonic() - start})
        return 2
    except FileNotFoundError as exc:
        atomic_write(Path(args.result_json), {"status": "failed", "error_code": "ARTIFACT_MISSING", "message": str(exc), "wall_time_s": time.monotonic() - start})
        return 4
    except Exception as exc:
        atomic_write(Path(args.result_json), {"status": "failed", "error_code": "TOOL_CRASHED", "message": str(exc), "wall_time_s": time.monotonic() - start})
        return 4
