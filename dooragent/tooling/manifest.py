"""Tool Manifest 加载：解析 configs/tool-manifests/<role>/<tool_id>.toml。

Manifest 字段（方案 14.1 节）：
  tool_id / interface_version / implementation / entrypoint /
  request_schema / result_schema / capabilities / required_env /
  timeout_s / concurrency_limit / healthcheck /
  license_id / third_party_disclosure
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from dooragent.errors import DoorAgentError, ErrorCode


@dataclass(slots=True)
class ToolManifest:
    tool_id: str
    interface_version: str
    implementation: str            # adapter | builtin | external | script | mock
    entrypoint: str
    request_schema: str
    result_schema: str
    capabilities: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    timeout_s: int = 600
    concurrency_limit: int = 1
    healthcheck: str = ""
    license_id: str = ""
    third_party_disclosure: str = ""
    role: str = ""                 # master|a1|a2|a3，加载时填入
    manifest_path: str = ""        # 相对项目根，加载时填入

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolManifest":
        required = ("tool_id", "interface_version", "implementation", "entrypoint",
                    "request_schema", "result_schema")
        for k in required:
            if k not in data:
                raise DoorAgentError(
                    ErrorCode.INVALID_REQUEST,
                    f"tool manifest missing field: {k}",
                )
        allowed_impl = {"adapter", "builtin", "external", "script", "mock"}
        if data["implementation"] not in allowed_impl:
            raise DoorAgentError(
                ErrorCode.INVALID_REQUEST,
                f"invalid implementation: {data['implementation']}",
            )
        return cls(
            tool_id=str(data["tool_id"]),
            interface_version=str(data["interface_version"]),
            implementation=str(data["implementation"]),
            entrypoint=str(data["entrypoint"]),
            request_schema=str(data["request_schema"]),
            result_schema=str(data["result_schema"]),
            capabilities=list(data.get("capabilities", [])),
            required_env=list(data.get("required_env", [])),
            timeout_s=int(data.get("timeout_s", 600)),
            concurrency_limit=int(data.get("concurrency_limit", 1)),
            healthcheck=str(data.get("healthcheck", "")),
            license_id=str(data.get("license_id", "")),
            third_party_disclosure=str(data.get("third_party_disclosure", "")),
        )


def load_manifest(path: Path) -> ToolManifest:
    if not path.exists():
        raise DoorAgentError(ErrorCode.INVALID_REQUEST, f"manifest not found: {path}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    m = ToolManifest.from_dict(data)
    m.manifest_path = str(path)
    parts = path.parts
    for role in ("master", "a1", "a2", "a3"):
        if role in parts:
            m.role = role
            break
    return m


def load_all_manifests(manifest_dirs: list[Path]) -> list[ToolManifest]:
    result: list[ToolManifest] = []
    seen: set[str] = set()
    for d in manifest_dirs:
        if not d.exists():
            continue
        for toml_path in sorted(d.glob("*.toml")):
            manifest = load_manifest(toml_path)
            if manifest.tool_id in seen:
                raise DoorAgentError(
                    ErrorCode.INVALID_REQUEST,
                    f"duplicate tool_id across manifests: {manifest.tool_id}",
                )
            seen.add(manifest.tool_id)
            result.append(manifest)
    return result
