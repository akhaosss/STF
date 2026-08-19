#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${REPO_ROOT}/config/roundabout_2b.yaml"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "用法：./scripts/run_roundabout_behavior.sh"
    echo "Behavior参考控制器示例：每个场景定义运行一次，不检查或启动TCP。"
    echo "动态参数统一编辑：${CONFIG_PATH}"
    exit 0
fi
if (($# != 0)); then
    echo "错误：动态参数统一由 ${CONFIG_PATH} 管理，启动脚本不接受其他参数。" >&2
    exit 2
fi

command -v conda >/dev/null 2>&1 || {
    echo "错误：找不到 conda 命令。" >&2
    exit 1
}

CONDA_ENV="$(awk '$1 == "conda_env:" {print $2; exit}' "$CONFIG_PATH" | tr -d "\"'")"
if [[ -z "$CONDA_ENV" ]]; then
    echo "错误：无法从 ${CONFIG_PATH} 读取 environment.conda_env。" >&2
    exit 2
fi

exec conda run --no-capture-output -n "$CONDA_ENV" \
    python "$SCRIPT_DIR/roundabout_launcher.py" run-behavior --config "$CONFIG_PATH"
