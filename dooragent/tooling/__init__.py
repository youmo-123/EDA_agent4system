"""Tool 通用调用框架。

- registry：Tool ID → Manifest → Runner 的注册中心
- manifest：TOML manifest 加载与 Schema 校验
- adapter：可选专用 Adapter 基类；仅当外部协议特殊时使用
- runner：通用 subprocess Runner（含超时、取消、环境白名单）
- health：状态机 DECLARED_NOT_BOUND → BOUND_UNVERIFIED → HEALTHY/DEGRADED/UNAVAILABLE
- result：Tool Result 封装与状态映射
"""

from dooragent.tooling.registry import ToolRegistry, ToolBinding
from dooragent.tooling.manifest import ToolManifest, load_all_manifests, load_manifest
from dooragent.tooling.adapter import BaseAdapter, MockAdapter
from dooragent.tooling.health import ToolHealthState, health_of
from dooragent.tooling.runner import ScriptRunner, RunnerResult
from dooragent.tooling.result import ToolResult, ToolStatus

__all__ = [
    "ToolRegistry",
    "ToolBinding",
    "ToolManifest",
    "load_manifest",
    "load_all_manifests",
    "BaseAdapter",
    "MockAdapter",
    "ToolHealthState",
    "health_of",
    "ScriptRunner",
    "RunnerResult",
    "ToolResult",
    "ToolStatus",
]
