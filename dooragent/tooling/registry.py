"""Tool Registry：Tool ID 唯一注册中心。

- 从 configs/tool-manifests/**/*.toml 加载所有 Manifest
- 根据 implementation 选择 Runner 或 Adapter
- 提供 health/list/invoke 接口
"""
from __future__ import annotations

import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode
from dooragent.tooling.adapter import BaseAdapter, MockAdapter
from dooragent.tooling.health import ToolHealthState, health_of
from dooragent.tooling.manifest import ToolManifest, load_all_manifests
from dooragent.tooling.result import ToolResult, ToolStatus
from dooragent.tooling.runner import ScriptRunner, runner_result_to_tool_result


@dataclass(slots=True)
class ToolBinding:
    manifest: ToolManifest
    health_state: ToolHealthState
    adapter: BaseAdapter | None = None


class ToolRegistry:
    """加载与调用所有 Tool。

    strict=True 时未注册 Tool ID 一律拒绝调用。
    """

    def __init__(
        self,
        *,
        project_root: Path,
        manifest_dirs: list[Path],
        strict: bool = True,
        runner: ScriptRunner | None = None,
    ):
        self.project_root = project_root
        self.strict = strict
        self.runner = runner or ScriptRunner()
        self._bindings: dict[str, ToolBinding] = {}
        self._adapters: dict[str, BaseAdapter] = {}
        for m in load_all_manifests(manifest_dirs):
            self._bindings[m.tool_id] = ToolBinding(
                manifest=m,
                health_state=health_of(m, project_root),
            )

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def list_ids(self) -> list[str]:
        return sorted(self._bindings.keys())

    def get(self, tool_id: str) -> ToolBinding:
        if tool_id not in self._bindings:
            if self.strict:
                raise DoorAgentError(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    f"tool not registered: {tool_id}",
                )
        return self._bindings[tool_id]

    def health(self, tool_id: str) -> dict[str, Any]:
        b = self.get(tool_id)
        return {
            "tool_id": tool_id,
            "state": b.health_state.value,
            "implementation": b.manifest.implementation,
        }

    def health_all(self) -> list[dict[str, Any]]:
        return [self.health(tid) for tid in self.list_ids()]

    def register_adapter(self, tool_id: str, adapter: BaseAdapter) -> None:
        """允许在运行时把某 Tool 绑定到自定义 Adapter（例如测试）。"""
        if tool_id not in self._bindings:
            raise DoorAgentError(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                f"cannot register adapter for unknown tool: {tool_id}",
            )
        self._bindings[tool_id].adapter = adapter
        self._bindings[tool_id].health_state = ToolHealthState.HEALTHY

    # ------------------------------------------------------------------ #
    # Invocation
    # ------------------------------------------------------------------ #
    def invoke(self, request: dict[str, Any]) -> ToolResult:
        tool_id = request.get("tool_id", "")
        if not tool_id:
            raise DoorAgentError(ErrorCode.INVALID_REQUEST, "tool_id missing")
        binding = self.get(tool_id)
        m = binding.manifest

        # 未健康：直接返回 UNAVAILABLE，禁止伪造成功
        if binding.health_state == ToolHealthState.DECLARED_NOT_BOUND:
            return ToolResult.unavailable(
                tool_id, request.get("request_id", "-"),
                f"tool {tool_id} not bound: entrypoint missing",
            )

        # 优先使用注入的 Adapter
        if binding.adapter is not None:
            return binding.adapter.invoke(request)

        impl = m.implementation
        if impl == "mock":
            return MockAdapter(tool_id=tool_id).invoke(request)
        if impl == "script":
            return self._invoke_script(m, request)
        if impl in ("builtin", "adapter", "external"):
            # builtin/adapter/external 未注入 adapter 时视为未实现
            return ToolResult.unsupported(
                tool_id, request.get("request_id", "-"),
                f"tool {tool_id} implementation={impl} has no adapter bound",
            )
        raise DoorAgentError(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            f"unknown implementation: {impl}",
        )

    # ------------------------------------------------------------------ #
    def _invoke_script(self, m: ToolManifest, request: dict[str, Any]) -> ToolResult:
        """把 request 写为 request.json，让 script 以统一 CLI 消费。"""
        params = request.get("parameters") or {}
        output_dir = request.get("output_dir")
        workspace_root = request.get("workspace_root", ".")
        request_id = request.get("request_id", "req-unknown")
        timeout_s = request.get("timeout_s") or m.timeout_s

        # 决定 work_dir（相对 workspace_root）
        work_dir_rel = output_dir or f"artifacts/tool-runs/{m.tool_id}/{request_id}"
        ws_root = (self.project_root / workspace_root).resolve()
        work_dir_abs = (ws_root / work_dir_rel).resolve()
        work_dir_abs.mkdir(parents=True, exist_ok=True)

        request_path = work_dir_abs / "request.json"
        result_path = work_dir_abs / "result.json"
        request_path.write_text(
            json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        entry = m.entrypoint
        argv = shlex.split(entry)
        if argv and argv[0].endswith(".py"):
            argv = [sys.executable] + argv
        # 追加统一 CLI 参数
        argv += [
            "--request-json", str(request_path),
            "--result-json", str(result_path),
            "--work-dir", str(work_dir_abs),
            "--timeout-s", str(int(timeout_s)),
        ]
        r = self.runner.run(argv, cwd=self.project_root, timeout_s=timeout_s + 30)
        # 优先信任脚本写出的 result.json；否则用 exit_code 兜底
        if result_path.exists():
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
                data.setdefault("tool_id", m.tool_id)
                data.setdefault("tool_interface_version", m.interface_version)
                data.setdefault("request_id", request_id)
                data.setdefault("status", ToolStatus.COMPLETED.value if r.exit_code == 0 else ToolStatus.FAILED.value)
                data.setdefault("wall_time_s", r.wall_time_s)
                return ToolResult(
                    tool_id=data["tool_id"],
                    tool_interface_version=data["tool_interface_version"],
                    request_id=data["request_id"],
                    status=ToolStatus(data["status"]),
                    output_artifact_refs=list(data.get("output_artifact_refs", [])),
                    raw_metrics=dict(data.get("raw_metrics", {})),
                    diagnostics=list(data.get("diagnostics", [])),
                    wall_time_s=float(data.get("wall_time_s", 0.0)),
                    error=data.get("error"),
                    error_code=data.get("error_code"),
                    tool_versions=dict(data.get("tool_versions", {})),
                    command_refs=list(data.get("command_refs", [])),
                )
            except Exception:
                pass
        return runner_result_to_tool_result(
            m.tool_id, m.interface_version, request_id, r,
        )
