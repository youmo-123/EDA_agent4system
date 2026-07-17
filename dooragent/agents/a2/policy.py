"""A2 Policy：coverage 反馈策略选择。

方案 15.2 表格：
| A1 反馈 | A2 被优化的环节 |
| reachable but rare | 提高相关场景权重 |
| suspected unreachable | 切换到约束求解/可达性检查 |
| observability gap | 调整 monitor/sampling |
| depth insufficient | 增加前缀或序列长度 |
| hotspot expensive | 优先小定向集合 |
| failure clustered | 切换 operator |
"""
from __future__ import annotations

from typing import Any


class A2Policy:
    def next_generation_strategy(self, gap_analysis: dict[str, Any]) -> str:
        """从 gap_analysis 推断下一策略；返回 selected_generation_strategy 枚举之一。"""
        reachable = gap_analysis.get("reachable_gaps", [])
        unreachable = gap_analysis.get("suspected_unreachable", [])
        observability = gap_analysis.get("observability_gaps", [])
        if unreachable:
            return "constraint-solver"
        if observability:
            return "directed"
        if reachable:
            return "random-reweight"
        return "request-info"


# ---------------------------------------------------------------------------- #
# a2_strategy_selector Manifest 的 builtin entrypoint 引用点
# ---------------------------------------------------------------------------- #
def select_strategy(request: dict[str, Any]) -> dict[str, Any]:
    """输入 gap_analysis payload，输出 selected_generation_strategy。"""
    policy = A2Policy()
    ctx = request.get("parameters", {}).get("context", {}) if isinstance(request, dict) else {}
    return {"selected_generation_strategy": policy.next_generation_strategy(ctx)}
