"""MasterFacade：产品 Runtime 唯一调用入口。

    master_facade.execute(master_task) → AgentResult

对 A1/A2/A3 的调度由 orchestration 完成；Facade 只暴露稳定语义。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from dooragent.agents.contracts import AgentResult, AgentTask
from dooragent.agents.master.agent import MasterAgent
from dooragent.agents.master.context import MasterContext
from dooragent.agents.master.policy import MasterPolicy


class MasterFacade:
    def __init__(self, context: MasterContext, agent: MasterAgent | None = None,
                 policy: MasterPolicy | None = None):
        self.ctx = context
        self.agent = agent or MasterAgent(
            registry=context.tool_registry,
            product_run_root=context.product_run_root,
        )
        self.policy = policy or MasterPolicy()

    def execute(self, task: AgentTask | dict[str, Any]) -> AgentResult:
        if isinstance(task, dict):
            task = AgentTask.from_dict(task)
        return self.agent.execute(task)

    def route(self, agent_task: dict[str, Any]):
        return self.policy.route_task(agent_task)
