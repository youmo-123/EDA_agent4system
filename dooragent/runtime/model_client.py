"""Master / A1 / A2 / A3 统一模型调用入口。

约束（见方案第 14.7 节）：
1. Provider / Key / URL / Model / Timeout / Retries 全部从环境变量读取
2. API key 不允许出现在 repr / 异常 / 日志 / 事件 payload / artifact 中
3. 支持的 provider：
   - `openai_compatible`：真实 HTTP 调用；缺失依赖时降级为 UNAVAILABLE
   - `mock`：确定性 mock，仅用于测试与调试；不出网
4. `health()` 校验配置完整性、格式与 mock/真实 provider 的可用性
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from dooragent.errors import DoorAgentError, ErrorCode
from dooragent.runtime.model_config import ModelSettings
from dooragent.runtime.secret_redactor import redact

LOG = logging.getLogger("dooragent.model_client")


@dataclass(slots=True)
class ModelResponse:
    content: str
    provider: str
    model: str
    request_id: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelClient:
    """线程安全无状态客户端；每次 complete 独立请求。"""

    def __init__(self, settings: ModelSettings, *, transport: Callable | None = None):
        self.settings = settings
        self._transport = transport  # 允许测试注入

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #
    def health(self) -> dict[str, Any]:
        if not self.settings.provider:
            return {"state": "UNAVAILABLE", "reason": "provider empty"}
        if self.settings.provider == "mock":
            return {"state": "HEALTHY", "provider": "mock"}
        if self.settings.provider == "openai_compatible":
            missing = []
            if not self.settings.api_key:
                missing.append("api_key")
            if not self.settings.base_url:
                missing.append("base_url")
            if not self.settings.model_name:
                missing.append("model_name")
            if missing:
                return {"state": "UNAVAILABLE", "reason": f"missing: {missing}"}
            return {"state": "BOUND_UNVERIFIED", "provider": self.settings.provider}
        return {"state": "UNAVAILABLE", "reason": f"unknown provider {self.settings.provider}"}

    # ------------------------------------------------------------------ #
    # Complete
    # ------------------------------------------------------------------ #
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ModelResponse:
        metadata = dict(metadata or {})
        req_id = metadata.get("request_id") or f"model-req-{int(time.time() * 1000)}"
        t0 = time.time()

        provider = self.settings.provider
        if provider == "mock":
            resp = self._mock_complete(messages, metadata, req_id)
        elif provider == "openai_compatible":
            resp = self._openai_complete(messages, metadata, req_id)
        else:
            raise DoorAgentError(
                ErrorCode.MODEL_CONFIG_MISSING,
                f"unknown provider: {provider}",
            )

        resp.latency_ms = int((time.time() - t0) * 1000)
        LOG.info(
            "model.request provider=%s model=%s req_id=%s latency_ms=%d "
            "prompt=%d completion=%d workflow=%s",
            resp.provider,
            resp.model,
            resp.request_id,
            resp.latency_ms,
            resp.prompt_tokens,
            resp.completion_tokens,
            metadata.get("workflow_id", "-"),
        )
        return resp

    # ------------------------------------------------------------------ #
    # Providers
    # ------------------------------------------------------------------ #
    def _mock_complete(
        self,
        messages: list[dict[str, str]],
        metadata: dict[str, Any],
        req_id: str,
    ) -> ModelResponse:
        """确定性 mock：返回带上下文摘要的固定内容，用于测试与骨架冒烟。"""
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        summary = (last_user or "").strip().splitlines()[:2]
        content = json.dumps(
            {
                "provider": "mock",
                "role_hint": metadata.get("agent_role", ""),
                "summary": summary,
                "action": "noop",
                "note": "This is a mock model response for scaffold/testing.",
            },
            ensure_ascii=False,
        )
        return ModelResponse(
            content=content,
            provider="mock",
            model=self.settings.model_name or "mock",
            request_id=req_id,
            prompt_tokens=sum(len(m.get("content", "")) for m in messages),
            completion_tokens=len(content),
            metadata={"workflow_id": metadata.get("workflow_id", "")},
        )

    def _openai_complete(
        self,
        messages: list[dict[str, str]],
        metadata: dict[str, Any],
        req_id: str,
    ) -> ModelResponse:
        """真实 HTTP 调用；未安装 httpx / urllib 缺失时返回 UNAVAILABLE。"""
        if self._transport is not None:
            content = self._transport(
                base_url=self.settings.base_url,
                api_key=self.settings.api_key,
                model=self.settings.model_name,
                messages=messages,
                timeout_s=self.settings.timeout_s,
            )
            return ModelResponse(
                content=content,
                provider=self.settings.provider,
                model=self.settings.model_name,
                request_id=req_id,
                metadata={"workflow_id": metadata.get("workflow_id", "")},
            )
        try:
            import urllib.request  # noqa: WPS433
            import urllib.error  # noqa: WPS433
        except Exception as exc:  # pragma: no cover
            raise DoorAgentError(
                ErrorCode.MODEL_CALL_FAILED,
                f"urllib unavailable: {exc}",
            )
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        body = json.dumps(
            {"model": self.settings.model_name, "messages": messages}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.settings.timeout_s) as resp:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw)
                    choice = (data.get("choices") or [{}])[0]
                    content = (choice.get("message") or {}).get("content", "")
                    usage = data.get("usage") or {}
                    return ModelResponse(
                        content=content,
                        provider=self.settings.provider,
                        model=self.settings.model_name,
                        request_id=req_id,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        metadata={"workflow_id": metadata.get("workflow_id", "")},
                    )
            except Exception as exc:  # noqa: BLE001
                if attempt >= self.settings.max_retries:
                    # 脱敏后再包装错误
                    msg = redact(str(exc))
                    raise DoorAgentError(ErrorCode.MODEL_CALL_FAILED, msg)
                time.sleep(min(2 ** attempt, 8))
        raise DoorAgentError(ErrorCode.MODEL_CALL_FAILED, "exhausted retries")


_AUTH_HEADER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*)([^\s]+)")


def scrub_headers(text: str) -> str:
    """辅助：把 Authorization header 值抹掉；配合 secret_redactor 使用。"""
    return _AUTH_HEADER_RE.sub(r"\1***REDACTED***", text)
