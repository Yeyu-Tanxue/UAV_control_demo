#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
python_bin="${repo_dir}/.venv/bin/python"
model_path="${RAIL_MODEL:-${repo_dir}/models/rail_spring_ncnn_model}"
px4_address="${PX4_ADDRESS:-serial:///dev/ttyAMA0:921600}"

if [[ ! -x "${python_bin}" ]]; then
    echo "Python environment missing; run ./scripts/setup_rpi_vision.sh first." >&2
    exit 1
fi

if [[ ! -e "${model_path}" ]]; then
    echo "Local rail model missing: ${model_path}" >&2
    echo "Set RAIL_MODEL to the local .pt, ONNX, or NCNN model path." >&2
    exit 1
fi

exec "${python_bin}" -m uav_demo.onboard_cli \
    --backend mavsdk \
    --confirm-flight \
    --system-address "${px4_address}" \
    --camera-source picamera2 \
    --model "${model_path}" \
    --device cpu \
    --output-dir "${repo_dir}/captures/visual_control" \
    "$@"
