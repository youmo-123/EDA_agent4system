"""A1 Policy：诊断覆盖 vs 正式覆盖率的边界判断、瓶颈分析优先级等。"""
from __future__ import annotations

from typing import Any


class A1Policy:
    def diagnostic_only(self, request: dict[str, Any]) -> bool:
        """A1 只提供诊断覆盖，不冒充 A2 正式覆盖率。"""
        return True

    def profile_needed_for_bottleneck(self) -> bool:
        return True
