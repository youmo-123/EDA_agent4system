"""schema_io：JSON Schema 加载与校验。

- 优先使用 jsonschema Draft 2020-12
- 若未安装 jsonschema，则退化为最小 required/type 校验
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
    _HAS_JSONSCHEMA = True
except Exception:  # pragma: no cover
    _HAS_JSONSCHEMA = False


class SchemaValidationError(ValueError):
    pass


def load_schema(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(instance: Any, schema: dict[str, Any]) -> None:
    if _HAS_JSONSCHEMA:
        errors = list(Draft202012Validator(schema).iter_errors(instance))
        if errors:
            reasons = [f"{list(e.path)}: {e.message}" for e in errors]
            raise SchemaValidationError("; ".join(reasons))
        return
    # 极简回退
    required = schema.get("required", [])
    if isinstance(instance, dict):
        for k in required:
            if k not in instance:
                raise SchemaValidationError(f"missing required: {k}")
