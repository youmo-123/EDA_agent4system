"""command：参数数组式启动 subprocess，禁止 Shell 拼接与未白名单环境变量。"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


DEFAULT_ENV_WHITELIST = (
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR",
    "DOORAGENT_YOSYS_BIN", "DOORAGENT_ABC_BIN", "DOORAGENT_OPENSTA_BIN",
    "DOORAGENT_ICARUS_IVERILOG_BIN", "DOORAGENT_ICARUS_VVP_BIN",
    "DOORAGENT_VCS_BIN", "DOORAGENT_URG_BIN",
)


@dataclass(slots=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    wall_time_s: float
    timed_out: bool = False
    cancelled: bool = False
    command: list[str] = field(default_factory=list)


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout_s: float | None = None,
    env_whitelist: Sequence[str] = DEFAULT_ENV_WHITELIST,
    extra_env: dict[str, str] | None = None,
    stdin_data: bytes | None = None,
    kill_after_s: float = 5.0,
) -> CommandResult:
    if not argv:
        raise ValueError("empty argv")
    env = {k: v for k, v in os.environ.items() if k in env_whitelist}
    if extra_env:
        env.update(extra_env)
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
        _kill_group(proc)
        try:
            stdout_b, stderr_b = proc.communicate(timeout=kill_after_s)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
            stdout_b, stderr_b = proc.communicate()
        exit_code = 124
    except KeyboardInterrupt:  # pragma: no cover
        cancelled = True
        _kill_group(proc)
        stdout_b, stderr_b = proc.communicate()
        exit_code = 130
    return CommandResult(
        exit_code=exit_code,
        stdout=stdout_b.decode("utf-8", errors="replace") if stdout_b else "",
        stderr=stderr_b.decode("utf-8", errors="replace") if stderr_b else "",
        wall_time_s=time.time() - t0,
        timed_out=timed_out,
        cancelled=cancelled,
        command=list(argv),
    )


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        if sys.platform != "win32":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:  # pragma: no cover
            proc.terminate()
    except Exception:  # pragma: no cover
        proc.kill()
