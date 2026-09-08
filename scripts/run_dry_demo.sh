#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
python_bin="${repo_dir}/.venv/bin/python"

if [[ ! -x "${python_bin}" ]]; then
    echo "Python environment missing; run ./scripts/setup_python.sh first." >&2
    exit 1
fi

exec "${python_bin}" -m uav_demo --backend dry-run "$@"
