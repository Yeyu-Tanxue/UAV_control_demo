#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
px4_dir="${PX4_AUTOPILOT_DIR:-${HOME}/PX4-Autopilot}"
gazebo_dir="${repo_dir}/simulation/gazebo"
world_file="${gazebo_dir}/worlds/rail_demo.sdf"
px4_gazebo_dir="${px4_dir}/Tools/simulation/gz"
px4_gazebo_plugins_dir="${px4_dir}/build/px4_sitl_default/src/modules/simulation/gz_plugins"

if [[ ! -d "${px4_dir}/.git" ]]; then
    echo "PX4 repository not found: ${px4_dir}" >&2
    echo "Set PX4_AUTOPILOT_DIR to the PX4-Autopilot checkout." >&2
    exit 1
fi

python3 "${repo_dir}/tools/generate_gazebo_rail_world.py" --check

export PX4_GZ_MODELS="${px4_gazebo_dir}/models"
export PX4_GZ_WORLDS="${gazebo_dir}/worlds"
export GZ_SIM_RESOURCE_PATH="${gazebo_dir}/worlds:${gazebo_dir}/models:${px4_gazebo_dir}/models:${px4_gazebo_dir}/worlds${GZ_SIM_RESOURCE_PATH:+:${GZ_SIM_RESOURCE_PATH}}"
export GZ_SIM_SERVER_CONFIG_PATH="${px4_gazebo_dir}/server.config"
if [[ -d "${px4_gazebo_plugins_dir}" ]]; then
    export GZ_SIM_SYSTEM_PLUGIN_PATH="${px4_gazebo_plugins_dir}${GZ_SIM_SYSTEM_PLUGIN_PATH:+:${GZ_SIM_SYSTEM_PLUGIN_PATH}}"
fi
export PX4_GZ_STANDALONE=1
export PX4_GZ_WORLD="rail_demo"
export PX4_GZ_MODEL_POSE="${PX4_GZ_MODEL_POSE:--13,-3,0.2,0,0,0}"

gazebo_server_pid=""
gazebo_gui_pid=""

cleanup() {
    if [[ -n "${gazebo_gui_pid}" ]] && kill -0 "${gazebo_gui_pid}" 2>/dev/null; then
        kill "${gazebo_gui_pid}" 2>/dev/null || true
        wait "${gazebo_gui_pid}" 2>/dev/null || true
    fi

    if [[ -n "${gazebo_server_pid}" ]] && kill -0 "${gazebo_server_pid}" 2>/dev/null; then
        kill "${gazebo_server_pid}" 2>/dev/null || true
        wait "${gazebo_server_pid}" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

echo "Starting PX4 X500 in rail_demo"
echo "Track: 30 m, standard gauge 1.435 m, no snow"
echo "Spawn pose: ${PX4_GZ_MODEL_POSE}"

gz sim -r -s "${world_file}" &
gazebo_server_pid=$!

if [[ -z "${HEADLESS:-}" ]]; then
    gz sim -g >/dev/null 2>&1 &
    gazebo_gui_pid=$!
fi

cd "${px4_dir}"
make px4_sitl gz_x500
