#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${REPO_ROOT}/config/roundabout_2b.yaml"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || $# -lt 1 || $# -gt 2 ]]; then
    echo "用法：./scripts/view_roundabout_run.sh <telemetry.csv.gz|summary.json|旧2b_result.pkl> [场景JSON]"
    echo "示例：./scripts/view_roundabout_run.sh runs/.../trial_01/attempt_01/telemetry.csv.gz"
    exit $(( $# >= 1 ? 0 : 2 ))
fi

CONDA_ENV="$(awk '$1 == "conda_env:" {print $2; exit}' "$CONFIG_PATH" | tr -d "\"'")"
HOST="$(awk '$1 == "host:" {print $2; exit}' "$CONFIG_PATH" | tr -d "\"'")"
PORT="$(awk '$1 == "port:" {print $2; exit}' "$CONFIG_PATH" | tr -d "\"'")"
CONDA_ENV="${CONDA_ENV:-carla0916}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-2000}"

ARGS=("$REPO_ROOT/tools/view_roundabout_run.py" "$1" --host "$HOST" --port "$PORT")
if [[ $# -eq 2 ]]; then
    ARGS+=(--scenario-config "$2")
fi

cd "$REPO_ROOT"
exec conda run --no-capture-output -n "$CONDA_ENV" python -u "${ARGS[@]}"
