#!/usr/bin/env bash
set -euo pipefail

px4_dir="${PX4_AUTOPILOT_DIR:-${HOME}/PX4-Autopilot}"
uav_demo_target="${UAV_DEMO_PX4_TARGET:-gz_x500}"

if [[ ! -d "${px4_dir}/.git" ]]; then
    echo "PX4 repository not found: ${px4_dir}" >&2
    echo "Set PX4_AUTOPILOT_DIR to the PX4-Autopilot checkout." >&2
    exit 1
fi

cd "${px4_dir}"
echo "Starting PX4 SITL target: ${uav_demo_target}"
exec make px4_sitl "${uav_demo_target}"
