#!/usr/bin/env bash
# A2 unified entrypoint: locate Python and exec run.py; no business logic here.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${DOORAGENT_PYTHON:-$(command -v python3)}"
if [[ -z "${PYTHON}" ]]; then
    echo "[a2 run.sh] error: python3 not found" >&2
    exit 2
fi
exec "${PYTHON}" "${SCRIPT_DIR}/run.py" "$@"
