#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
px4_dir="${PX4_AUTOPILOT_DIR:-${HOME}/PX4-Autopilot}"
gazebo_dir="${repo_dir}/simulation/gazebo"
world_file="${gazebo_dir}/worlds/rail_demo_realistic.sdf"
px4_gazebo_dir="${px4_dir}/Tools/simulation/gz"
px4_gazebo_plugins_dir="${px4_dir}/build/px4_sitl_default/src/modules/simulation/gz_plugins"

if [[ ! -d "${px4_dir}/.git" ]]; then
    echo "PX4 repository not found: ${px4_dir}" >&2
    echo "Set PX4_AUTOPILOT_DIR to the PX4-Autopilot checkout." >&2
    exit 1
fi

if [[ ! -f "${gazebo_dir}/models/railway_straight_realistic/meshes/straight_track.glb" ]]; then
    echo "Straight-track GLB is missing from the Gazebo model package." >&2
    exit 1
fi

# PX4 loads the selected vehicle directly from this directory. Point it at
# the repository first so our pitched x500_mono_cam model is actually used;
# nested stock models still resolve through GZ_SIM_RESOURCE_PATH below.
export PX4_GZ_MODELS="${gazebo_dir}/models"
export PX4_GZ_WORLDS="${gazebo_dir}/worlds"
export GZ_SIM_RESOURCE_PATH="${gazebo_dir}/worlds:${gazebo_dir}/models:${px4_gazebo_dir}/models:${px4_gazebo_dir}/worlds${GZ_SIM_RESOURCE_PATH:+:${GZ_SIM_RESOURCE_PATH}}"
export GZ_SIM_SERVER_CONFIG_PATH="${px4_gazebo_dir}/server.config"
if [[ -d "${px4_gazebo_plugins_dir}" ]]; then
    export GZ_SIM_SYSTEM_PLUGIN_PATH="${px4_gazebo_plugins_dir}${GZ_SIM_SYSTEM_PLUGIN_PATH:+:${GZ_SIM_SYSTEM_PLUGIN_PATH}}"
fi
export PX4_GZ_STANDALONE=1
export PX4_GZ_WORLD="rail_demo_realistic"
export PX4_GZ_MODEL_POSE="${PX4_GZ_MODEL_POSE:--16.85,0,0.2,0,0,0}"

gazebo_server_pid=""
gazebo_gui_pid=""

cleanup() {
    stop_child() {
        local child_pid="$1"
        if [[ -z "${child_pid}" ]] || ! kill -0 "${child_pid}" 2>/dev/null; then
            return
        fi
        kill "${child_pid}" 2>/dev/null || true
        for _ in {1..20}; do
            if ! kill -0 "${child_pid}" 2>/dev/null; then
                wait "${child_pid}" 2>/dev/null || true
                return
            fi
            sleep 0.1
        done
        kill -KILL "${child_pid}" 2>/dev/null || true
        wait "${child_pid}" 2>/dev/null || true
    }
    if [[ -n "${gazebo_gui_pid}" ]] && kill -0 "${gazebo_gui_pid}" 2>/dev/null; then
        stop_child "${gazebo_gui_pid}"
    fi

    if [[ -n "${gazebo_server_pid}" ]] && kill -0 "${gazebo_server_pid}" 2>/dev/null; then
        stop_child "${gazebo_server_pid}"
    fi
}

trap cleanup EXIT INT TERM

echo "Starting PX4 X500 mono-camera in rail_demo_realistic"
echo "Track: eight textured 4 m Part 1 modules, no curve, no turnout, no snow"
echo "Spawn pose: ${PX4_GZ_MODEL_POSE}"
echo "Camera: fixed 35 degrees forward-down, 110 degrees horizontal FOV"
echo "Camera spool: /tmp/uav_demo_camera"

rm -rf -- /tmp/uav_demo_camera
mkdir -p /tmp/uav_demo_camera

gz sim -r -s "${world_file}" &
gazebo_server_pid=$!

if [[ -z "${HEADLESS:-}" ]]; then
    gz sim -g >/dev/null 2>&1 &
    gazebo_gui_pid=$!
fi

cd "${px4_dir}"
make px4_sitl gz_x500_mono_cam
