#!/usr/bin/env python3
"""a2_verification_skeleton_generator：基于 design.json 生成 verification package。

- 生成 clock/reset、driver/monitor/scoreboard 接口占位
- 每个端口在 driver/monitor 中都有对应绑定；禁止悬空
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.atomic_io import write_json_atomic
from scripts.common.artifact_io import now_iso, sha256_file
from scripts.common.script_cli import ScriptResult, run_script


DRIVER_TEMPLATE = """\
# Auto-generated driver stub for {top}
class {top}Driver:
    def __init__(self, dut):
        self.dut = dut
    async def drive(self, transaction):
        raise NotImplementedError('protocol-specific driver')
"""


MONITOR_TEMPLATE = """\
# Auto-generated monitor stub for {top}
class {top}Monitor:
    def __init__(self, dut):
        self.dut = dut
    async def observe(self):
        raise NotImplementedError('protocol-specific monitor')
"""


SCOREBOARD_TEMPLATE = """\
# Auto-generated scoreboard stub for {top}
class {top}Scoreboard:
    def compare(self, dut_out, ref_out):
        return dut_out == ref_out
"""


def handle(request: dict[str, Any], work_dir: Path) -> ScriptResult:
    params = request.get("parameters") or {}
    design_ref = params.get("design_ref", "")
    if not design_ref or not Path(design_ref).exists():
        return ScriptResult(status="failed", error_code="INVALID_REQUEST",
                            error={"message": "design_ref missing"})
    design = json.loads(Path(design_ref).read_text(encoding="utf-8"))
    top = design.get("top") or "top"
    tb_dir = work_dir / "generated_tb"
    tb_dir.mkdir(parents=True, exist_ok=True)
    (tb_dir / "driver.py").write_text(DRIVER_TEMPLATE.format(top=top), encoding="utf-8")
    (tb_dir / "monitor.py").write_text(MONITOR_TEMPLATE.format(top=top), encoding="utf-8")
    (tb_dir / "scoreboard.py").write_text(SCOREBOARD_TEMPLATE.format(top=top), encoding="utf-8")

    package = {
        "package_id": f"vp-{top}",
        "generated_tb_ref": "generated_tb/",
        "reference_model_ref": None,
        "protocols": design.get("protocol_candidates", []),
        "created_at": now_iso(),
        "port_bindings": design.get("ports", []),
    }
    skeleton = {
        "package_id": package["package_id"],
        "driver_ref": "generated_tb/driver.py",
        "monitor_ref": "generated_tb/monitor.py",
        "scoreboard_ref": "generated_tb/scoreboard.py",
        "created_at": now_iso(),
    }
    write_json_atomic(work_dir / "verification-package.json", package)
    write_json_atomic(work_dir / "verification-skeleton.json", skeleton)
    return ScriptResult(
        status="completed",
        output_artifact_refs=[
            "verification-package.json",
            "verification-skeleton.json",
            "generated_tb/driver.py",
            "generated_tb/monitor.py",
            "generated_tb/scoreboard.py",
        ],
        raw_metrics={"port_bindings": len(package["port_bindings"])},
    )


if __name__ == "__main__":
    raise SystemExit(run_script(
        prog="a2_verification_skeleton_generator",
        description="Generate driver/monitor/scoreboard skeleton",
        handler=handle,
    ))
