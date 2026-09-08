#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "${script_dir}/.." && pwd)"
venv_dir="${repo_dir}/.venv"

python3 -m venv "${venv_dir}"
"${venv_dir}/bin/python" -m pip install \
    --disable-pip-version-check \
    --progress-bar off \
    -e "${repo_dir}[sim]"

echo "Python environment ready: ${venv_dir}"
