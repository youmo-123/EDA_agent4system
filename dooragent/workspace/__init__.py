"""Workspace 管理：Primary / Child Service Workspace 生命周期。

生命周期（方案 12.3）：
  CREATING → READY → ACTIVE → FROZEN → ARCHIVING → ARCHIVED | FAILED
"""

from dooragent.workspace.manager import (
    WorkspaceManager,
    WorkspaceKind,
    WorkspaceState,
)

__all__ = ["WorkspaceManager", "WorkspaceKind", "WorkspaceState"]
