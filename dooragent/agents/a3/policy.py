"""A3 Policy：Strategy 选择、Pareto 更新、search_mode 切换。

方案 15.5：默认 catalog；只有集成测试通过后才允许 evolutionary，
且必须能自动回退。
"""
from __future__ import annotations

from typing import Any


class A3Policy:
    def choose_strategy(self, *, history: list[dict[str, Any]],
                        catalog: list[dict[str, Any]]) -> str | None:
        """从 catalog 中选择尚未评价过的第一个 strategy_id。"""
        seen = {h.get("strategy_id") for h in history}
        for s in catalog:
            sid = s.get("strategy_id")
            if sid and sid not in seen:
                return sid
        return None  # 已耗尽

    def should_fallback_from_evolutionary(self, *, generations_without_improve: int,
                                          budget_remaining_s: float) -> bool:
        return generations_without_improve >= 3 or budget_remaining_s <= 0
