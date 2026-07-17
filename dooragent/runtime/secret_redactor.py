"""日志/事件/异常/artifact 中的密钥脱敏。

策略：
- 从环境变量收集敏感值（KEY/TOKEN/SECRET/DOORAGENT_MODEL_ 前缀）
- 覆盖 str / bytes / dict 等常见容器
- 对 Authorization / Cookie 头额外正则脱敏
- Redactor 是幂等的；不改动结构，只替换值
"""
from __future__ import annotations

import os
import re
from typing import Any

_REDACTION = "***REDACTED***"

_BEARER_RE = re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9._\-]+)")
_HEADER_RE = re.compile(
    r"(?i)(authorization|x-api-key|cookie|set-cookie)\s*[:=]\s*([^\r\n,;]+)"
)


def _sensitive_env_keys() -> list[str]:
    keys = []
    for k in os.environ:
        upper = k.upper()
        if (
            "KEY" in upper
            or "TOKEN" in upper
            or "SECRET" in upper
            or upper.startswith("DOORAGENT_MODEL_")
        ):
            keys.append(k)
    return keys


def secret_values() -> list[str]:
    """按长度降序返回一次可用于替换的敏感值列表。"""
    values: set[str] = set()
    for k in _sensitive_env_keys():
        v = os.environ.get(k, "")
        if v and len(v) >= 4:
            values.add(v)
    return sorted(values, key=len, reverse=True)


def redact(text: str) -> str:
    if not text:
        return text
    result = text
    for v in secret_values():
        result = result.replace(v, _REDACTION)
    # 先脱敏 Bearer 令牌，再脱敏整个 header 值（顺序无关，但两者互补）
    result = _BEARER_RE.sub(lambda m: f"{m.group(1)}{_REDACTION}", result)
    result = _HEADER_RE.sub(lambda m: f"{m.group(1)}: {_REDACTION}", result)
    return result


def redact_obj(obj: Any) -> Any:
    """对 dict / list / tuple / str 递归脱敏；其余类型原样返回。"""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(redact_obj(x) for x in obj)
    return obj
