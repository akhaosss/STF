#!/usr/bin/env bash

set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tcp_model_path="$project_dir/tcp/best_model.ckpt"

if [[ ! -f "$tcp_model_path" ]]; then
  echo "TCP checkpoint not found: $tcp_model_path" >&2
  exit 1
fi

cd "$project_dir"

conda run -n safebench python run.py \
  --input_dir ./save_scenarios \
  --town 1b \
  --scenario 1b \
  --model behavior \
  --resume \
  --video_dir ./videos/behavior

conda run -n safebench python run.py \
  --input_dir ./save_scenarios \
  --town 1b \
  --scenario 1b \
  --model tcp \
  --model_path ./tcp/best_model.ckpt \
  --resume \
  --video_dir ./videos/tcp