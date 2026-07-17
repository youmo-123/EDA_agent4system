"""通用 subprocess Runner：以参数数组启动、白名单环境变量、超时/取消。

方案约束（14.5.1 节）：
  - 不允许拼接 Shell 字符串
  - 环境变量白名单启动
  - 退出码语义：
      0=completed / 2=invalid request / 3=tool unavailable /
      4=tool failed / 5=output invalid / 124=timeout / 130=cancelled
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from dooragent.tooling.result import EXIT_CODE_MAP, ToolResult, ToolStatus


DEFAULT_ENV_WHITELIST = (
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR",
    "DOORAGENT_YOSYS_BIN", "DOORAGENT_ABC_BIN", "DOORAGENT_OPENSTA_BIN",
    "DOORAGENT_ICARUS_IVERILOG_BIN", "DOORAGENT_ICARUS_VVP_BIN",
    "DOORAGENT_VCS_BIN", "DOORAGENT_URG_BIN",
)


@dataclass(slots=True)
class RunnerResult:
    exit_code: int
    stdout: str
    stderr: str
    wall_time_s: float
    timed_out: bool = False
    cancelled: bool = False
    command: list[str] = field(default_factory=list)


class ScriptRunner:
    """启动一个外部脚本或可执行程序；返回 RunnerResult。

    - argv: 完整参数数组（第一个元素是可执行程序）
    - cwd: 工作目录（相对项目根或绝对路径）
    - timeout_s: 超时后 SIGTERM，再 SIGKILL
    - env_whitelist: 只把这些环境变量透传给子进程
    """

    def __init__(
        self,
        *,
        env_whitelist: Sequence[str] = DEFAULT_ENV_WHITELIST,
        kill_after_s: float = 5.0,
    ):
        self.env_whitelist = tuple(env_whitelist)
        self.kill_after_s = kill_after_s

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout_s: float | None = None,
        stdin_data: bytes | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> RunnerResult:
        if not argv:
            raise ValueError("empty argv")
        env = self._build_env(extra_env or {})
        t0 = time.time()
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd) if cwd else None,
            env=env,
            stdin=subprocess.PIPE if stdin_data else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if sys.platform != "win32" else None,
        )
        timed_out = False
        cancelled = False
        try:
            stdout_b, stderr_b = proc.communicate(input=stdin_data, timeout=timeout_s)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc)
            try:
                stdout_b, stderr_b = proc.communicate(timeout=self.kill_after_s)
            except subprocess.TimeoutExpired:  # pragma: no cover
                proc.kill()
                stdout_b, stderr_b = proc.communicate()
            exit_code = 124
        except KeyboardInterrupt:  # pragma: no cover
            cancelled = True
            self._kill_group(proc)
            stdout_b, stderr_b = proc.communicate()
            exit_code = 130
        wall = time.time() - t0
        return RunnerResult(
            exit_code=exit_code,
            stdout=stdout_b.decode("utf-8", errors="replace") if stdout_b else "",
            stderr=stderr_b.decode("utf-8", errors="replace") if stderr_b else "",
            wall_time_s=wall,
            timed_out=timed_out,
            cancelled=cancelled,
            command=list(argv),
        )

    # ------------------------------------------------------------------ #
    def _build_env(self, extra: dict[str, str]) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k in self.env_whitelist}
        env.update(extra)
        return env

    def _kill_group(self, proc: subprocess.Popen) -> None:
        try:
            if sys.platform != "win32":
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:  # pragma: no cover
                proc.terminate()
        except Exception:  # pragma: no cover
            proc.kill()


def runner_result_to_tool_result(
    tool_id: str,
    tool_interface_version: str,
    request_id: str,
    r: RunnerResult,
    *,
    output_artifact_refs: list[str] | None = None,
    tool_versions: dict | None = None,
) -> ToolResult:
    status = EXIT_CODE_MAP.get(r.exit_code, ToolStatus.FAILED)
    err_code = None
    error = None
    if status not in (ToolStatus.COMPLETED, ToolStatus.PARTIAL):
        err_code = _EXIT_CODE_TO_ERROR.get(r.exit_code, "TOOL_CRASHED")
        error = {
            "exit_code": r.exit_code,
            "stderr_excerpt": r.stderr[-2048:] if r.stderr else "",
        }
    return ToolResult(
        tool_id=tool_id,
        tool_interface_version=tool_interface_version,
        request_id=request_id,
        status=status,
        output_artifact_refs=output_artifact_refs or [],
        wall_time_s=r.wall_time_s,
        error=error,
        error_code=err_code,
        tool_versions=tool_versions or {},
        command_refs=[" ".join(r.command)],
    )


_EXIT_CODE_TO_ERROR = {
    2: "INVALID_REQUEST",
    3: "CAPABILITY_UNAVAILABLE",
    4: "TOOL_CRASHED",
    5: "SCHEMA_MISMATCH",
    124: "TOOL_TIMEOUT",
    130: "TOOL_CRASHED",
}
