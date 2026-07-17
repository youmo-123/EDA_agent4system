"""atomic_io：所有 script 写 JSON 时统一入口。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_json_atomic(target: Path, data: Any) -> Path:
    """先写 target.partial，fsync 后原子 rename 到 target；rename 后 fsync 目录。"""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".partial")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
    except OSError:  # pragma: no cover - some FS may not allow
        pass
    os.replace(tmp, target)
    try:
        dir_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:  # pragma: no cover
        pass
    return target


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
