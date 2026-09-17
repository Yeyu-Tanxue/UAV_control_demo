#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
python_bin="${repo_dir}/.venv/bin/python"

if [[ ! -x "${python_bin}" ]]; then
    echo "Python environment missing; run ./scripts/setup_python.sh first." >&2
    exit 1
fi

model_path="${repo_dir}/output/training-runs/rail-segmentation/l4r_spring_yolo26n_sanity/weights/best.pt"

if [[ ! -f "${model_path}" ]]; then
    echo "Spring rail model missing: ${model_path}" >&2
    exit 1
fi

"${python_bin}" -m uav_demo.onboard_cli \
    --backend mavsdk \
    --confirm-sitl \
    --camera-source gazebo \
    --camera-source-dir /tmp/uav_demo_camera \
    --model "${model_path}" \
    --device cpu \
    --output-dir "${repo_dir}/captures/visual_control" \
    "$@"

latest_run="$(find "${repo_dir}/captures/visual_control" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
if [[ -n "${latest_run}" && -f "${latest_run}/decisions.jsonl" ]]; then
    if ! "${python_bin}" "${repo_dir}/scripts/render_visual_decisions.py" \
        --decisions "${latest_run}/decisions.jsonl" \
        --model "${model_path}" \
        --last 3; then
        echo "Warning: flight completed, but visualization rendering failed." >&2
    fi
fi
