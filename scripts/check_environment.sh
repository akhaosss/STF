#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${REPO_ROOT}/config/roundabout_2b.yaml"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "用法：./scripts/check_environment.sh"
    echo "环境和动态参数来源：${CONFIG_PATH}"
    exit 0
fi
if (($# != 0)); then
    echo "错误：本脚本不接受参数；请修改 ${CONFIG_PATH}。" >&2
    exit 2
fi

command -v conda >/dev/null 2>&1 || {
    echo "错误：找不到conda命令。" >&2
    exit 1
}

CONDA_ENV="$(awk '$1 == "conda_env:" {print $2; exit}' "$CONFIG_PATH" | tr -d "\"'")"
if [[ -z "$CONDA_ENV" ]]; then
    echo "错误：无法从 ${CONFIG_PATH} 读取environment.conda_env。" >&2
    exit 2
fi

if ! conda run -n "$CONDA_ENV" python -c "import yaml" >/dev/null 2>&1; then
    echo "错误：环境 ${CONDA_ENV} 缺少PyYAML；请先执行：" >&2
    echo "  conda run -n ${CONDA_ENV} python -m pip install -r ${REPO_ROOT}/environment/requirements.txt" >&2
    exit 1
fi

exec conda run --no-capture-output -n "$CONDA_ENV" \
    env PYTHONDONTWRITEBYTECODE=1 \
    python "$SCRIPT_DIR/check_environment.py" --config "$CONFIG_PATH"
