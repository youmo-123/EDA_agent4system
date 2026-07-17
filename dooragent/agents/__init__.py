"""四个 Agent（Master / A1 / A2 / A3）统一模型。"""

from dooragent.agents.base import BaseAgent, AgentContext
from dooragent.agents.contracts import (
    AgentTask,
    AgentResult,
    AgentResultStatus,
    ArtifactRef,
    CapabilityState,
)

__all__ = [
    "BaseAgent",
    "AgentContext",
    "AgentTask",
    "AgentResult",
    "AgentResultStatus",
    "ArtifactRef",
    "CapabilityState",
]
