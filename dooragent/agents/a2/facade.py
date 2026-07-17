from __future__ import annotations
from typing import Any
from dooragent.agents.contracts import AgentResult, AgentTask
from dooragent.agents.a2.agent import A2Agent
from dooragent.agents.a2.context import A2Context


class A2Facade:
    def __init__(self, context: A2Context, agent: A2Agent | None = None):
        self.ctx = context
        self.agent = agent or A2Agent(
            registry=context.tool_registry,
            product_run_root=context.product_run_root,
        )

    def execute(self, task: AgentTask | dict[str, Any]) -> AgentResult:
        if isinstance(task, dict):
            task = AgentTask.from_dict(task)
        return self.agent.execute(task)
