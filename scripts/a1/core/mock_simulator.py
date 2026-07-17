"""Mock 编译/仿真内核。

- 生产环境请设置 DOORAGENT_A1_SIMULATOR_BIN 指向真实二进制并禁用 Mock。
- Mock 仅用于骨架测试；不会伪造覆盖率/瓶颈结论，只保证 Script 契约可跑通。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def is_real_simulator_available() -> bool:
    bin_path = os.environ.get("DOORAGENT_A1_SIMULATOR_BIN", "")
    return bool(bin_path) and Path(bin_path).exists()


@dataclass(slots=True)
class MockCompileResult:
    ok: bool
    error_lines: list[str]
    source_map: dict[str, Any]


@dataclass(slots=True)
class MockSimulationResult:
    ok: bool
    pass_count: int
    fail_count: int
    events_processed: int
    delta_cycles: int
    wall_time_s: float
    module_time_s: dict[str, float]


def mock_compile(rtl_files: list[str], top: str) -> MockCompileResult:
    error_lines = []
    missing = [f for f in rtl_files if not Path(f).exists()]
    if missing:
        error_lines.append(f"missing files: {missing}")
    if not top:
        error_lines.append("empty top")
    source_map = {top: {"instance": "top_i", "signals": []}}
    return MockCompileResult(ok=not error_lines, error_lines=error_lines, source_map=source_map)


def mock_simulate(*, tests: list[str], seed: int) -> MockSimulationResult:
    t0 = time.time()
    # 纯 mock：pass 全部，除非某 test 名以 "fail-" 开头
    pass_count = sum(1 for t in tests if not t.startswith("fail-"))
    fail_count = sum(1 for t in tests if t.startswith("fail-"))
    return MockSimulationResult(
        ok=True,
        pass_count=pass_count,
        fail_count=fail_count,
        events_processed=1000 * max(1, len(tests)),
        delta_cycles=100 * max(1, len(tests)),
        wall_time_s=time.time() - t0,
        module_time_s={"top": 0.001},
    )
