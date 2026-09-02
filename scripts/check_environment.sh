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

CONDA_ENV="$(awk '$1 == "conda_env:" {print $2; exit}' "$CONFIG_PATH" | tr -d "\"'")"
PYTHON_CMD=(python)
if [[ -n "$CONDA_ENV" ]]; then
    command -v conda >/dev/null 2>&1 || {
        echo "错误：YAML指定了Conda环境 ${CONDA_ENV}，但找不到conda命令。" >&2
        exit 1
    }
    PYTHON_CMD=(conda run --no-capture-output -n "$CONDA_ENV" python)
fi

if ! "${PYTHON_CMD[@]}" -c "import yaml" >/dev/null 2>&1; then
    echo "错误：当前Python环境缺少PyYAML；请先执行：" >&2
    echo "  python -m pip install -r ${REPO_ROOT}/environment/requirements.txt" >&2
    exit 1
fi

export PYTHONDONTWRITEBYTECODE=1
exec "${PYTHON_CMD[@]}" "$SCRIPT_DIR/check_environment.py" --config "$CONFIG_PATH"
