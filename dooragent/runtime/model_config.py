"""从环境变量加载模型配置。

优先级（见方案第 14.7 节）：
  角色专属环境变量 (DOORAGENT_<ROLE>_MODEL_NAME 等)
  → 全局 DOORAGENT_MODEL_* 环境变量
  → 缺少必需项则抛 MODEL_CONFIG_MISSING

Provider 支持：
  - `openai_compatible`：必须提供 api_key / base_url / model_name
  - `mock`：只需 provider=mock；不会出网
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode


@dataclass(slots=True)
class ModelSettings:
    provider: str
    api_key: str
    base_url: str
    model_name: str
    timeout_s: int = 120
    max_retries: int = 3
    extra: dict[str, Any] = field(default_factory=dict)

    # 屏蔽默认 repr 泄露 key
    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ModelSettings(provider={self.provider!r}, "
            f"base_url={self.base_url!r}, model_name={self.model_name!r}, "
            f"api_key='***', timeout_s={self.timeout_s}, "
            f"max_retries={self.max_retries})"
        )

    @classmethod
    def from_env(cls, agent_role: str) -> "ModelSettings":
        provider = os.environ.get("DOORAGENT_MODEL_PROVIDER", "").strip()
        api_key = os.environ.get("DOORAGENT_MODEL_API_KEY", "").strip()
        base_url = os.environ.get("DOORAGENT_MODEL_BASE_URL", "").strip()
        role_env = f"DOORAGENT_{agent_role.upper()}_MODEL_NAME"
        role_model = os.environ.get(role_env, "").strip()
        model_name = role_model or os.environ.get("DOORAGENT_MODEL_NAME", "").strip()
        timeout_s = int(os.environ.get("DOORAGENT_MODEL_TIMEOUT_S", "120"))
        max_retries = int(os.environ.get("DOORAGENT_MODEL_MAX_RETRIES", "3"))

        if not provider:
            raise DoorAgentError(
                ErrorCode.MODEL_CONFIG_MISSING,
                f"provider missing for {agent_role} (set DOORAGENT_MODEL_PROVIDER)",
            )

        if provider == "mock":
            return cls(
                provider="mock",
                api_key="",
                base_url="",
                model_name=model_name or "mock",
                timeout_s=timeout_s,
                max_retries=max_retries,
            )

        # 真实 provider 需齐全
        missing = [
            name
            for name, val in (
                ("api_key", api_key),
                ("base_url", base_url),
                ("model_name", model_name),
            )
            if not val
        ]
        if missing:
            raise DoorAgentError(
                ErrorCode.MODEL_CONFIG_MISSING,
                f"model config missing for {agent_role}: {missing}",
            )
        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            timeout_s=timeout_s,
            max_retries=max_retries,
        )
