"""相对路径解析与越根校验，产品全局统一使用 POSIX 相对路径。

规则（见方案第 12.2 节）：
- 所有持久化路径必须相对 `product_run_root` 或 `workspace_root`
- 禁止绝对路径、Windows 盘符、`..` 越根、空 segment、未受控 symlink
- Tool Runner / 专用 Adapter 可临时解析为绝对路径，写回 JSON 前必须重新相对化
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from dooragent.errors import DoorAgentError, ErrorCode


def ensure_relative_posix(path: str) -> PurePosixPath:
    """把字符串校验为合法 POSIX 相对路径，不合法则抛 PATH_OUTSIDE_WORKSPACE。"""
    if path is None or path == "":
        raise DoorAgentError(ErrorCode.PATH_OUTSIDE_WORKSPACE, "empty path")
    if len(path) >= 2 and path[1] == ":":
        raise DoorAgentError(
            ErrorCode.PATH_OUTSIDE_WORKSPACE, f"windows drive path rejected: {path}"
        )
    # 在字符串层面拒绝空 segment（PurePosixPath 会归一化 a//b）
    if "//" in path:
        raise DoorAgentError(
            ErrorCode.PATH_OUTSIDE_WORKSPACE, f"empty segment rejected: {path}"
        )
    pure = PurePosixPath(path)
    if pure.is_absolute():
        raise DoorAgentError(ErrorCode.PATH_OUTSIDE_WORKSPACE, f"absolute path rejected: {path}")
    if ".." in pure.parts:
        raise DoorAgentError(ErrorCode.PATH_OUTSIDE_WORKSPACE, f"parent-traversal rejected: {path}")
    if any(part == "" for part in pure.parts):
        raise DoorAgentError(ErrorCode.PATH_OUTSIDE_WORKSPACE, f"empty segment rejected: {path}")
    return pure


def resolve_under(root: Path, relative_path: str, *, follow_symlinks: bool = True) -> Path:
    """在 `root` 下解析 relative_path，任何越根都抛 PATH_OUTSIDE_WORKSPACE。"""
    ensure_relative_posix(relative_path)
    root_resolved = root.resolve()
    resolved = (root_resolved / relative_path)
    if follow_symlinks:
        resolved = resolved.resolve()
    try:
        common = os.path.commonpath([str(root_resolved), str(resolved)])
    except ValueError:
        raise DoorAgentError(
            ErrorCode.PATH_OUTSIDE_WORKSPACE, f"path escapes root: {relative_path}"
        )
    if common != str(root_resolved):
        raise DoorAgentError(
            ErrorCode.PATH_OUTSIDE_WORKSPACE, f"path escapes root: {relative_path}"
        )
    return resolved


def relativize_under(root: Path, absolute_path: Path) -> str:
    """把 absolute_path 相对化到 root，越根抛 PATH_OUTSIDE_WORKSPACE。"""
    root_resolved = root.resolve()
    ap = absolute_path.resolve()
    try:
        rel = ap.relative_to(root_resolved)
    except ValueError:
        raise DoorAgentError(
            ErrorCode.PATH_OUTSIDE_WORKSPACE,
            f"cannot relativize {absolute_path} under {root}",
        )
    return rel.as_posix()


def join_relative(*parts: str) -> str:
    """安全拼接多个相对路径段。"""
    combined = PurePosixPath()
    for p in parts:
        pp = ensure_relative_posix(p)
        combined = combined / pp
    ensure_relative_posix(combined.as_posix())
    return combined.as_posix()
