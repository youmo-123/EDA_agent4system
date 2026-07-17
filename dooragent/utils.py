from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from dooragent.errors import DoorAgentError, ErrorCode


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_relative_posix(path: str) -> PurePosixPath:
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or any(part == "" for part in pure.parts):
        raise DoorAgentError(ErrorCode.PATH_OUTSIDE_WORKSPACE, f"invalid relative path: {path}")
    if len(path) >= 2 and path[1] == ":":
        raise DoorAgentError(ErrorCode.PATH_OUTSIDE_WORKSPACE, f"windows drive path rejected: {path}")
    return pure


def resolve_under(root: Path, relative_path: str) -> Path:
    ensure_relative_posix(relative_path)
    root_resolved = root.resolve()
    resolved = (root_resolved / relative_path).resolve()
    if os.path.commonpath([root_resolved, resolved]) != str(root_resolved):
        raise DoorAgentError(ErrorCode.PATH_OUTSIDE_WORKSPACE, f"path escapes root: {relative_path}")
    return resolved


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    encoded = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with partial.open("w", encoding="utf-8") as fh:
        fh.write(encoded)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(partial, path)
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
