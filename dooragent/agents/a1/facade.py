from __future__ import annotations
from typing import Any
from dooragent.agents.contracts import AgentResult, AgentTask
from dooragent.agents.a1.agent import A1Agent
from dooragent.agents.a1.context import A1Context


class A1Facade:
    def __init__(self, context: A1Context, agent: A1Agent | None = None):
        self.ctx = context
        self.agent = agent or A1Agent(
            registry=context.tool_registry,
            product_run_root=context.product_run_root,
        )

    def execute(self, task: AgentTask | dict[str, Any]) -> AgentResult:
        if isinstance(task, dict):
            task = AgentTask.from_dict(task)
        return self.agent.execute(task)
