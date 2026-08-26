#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPYCACHEPREFIX=${TMPDIR:-/tmp}/ollama-control-pycache
test_root=$(mktemp -d)
trap 'rm -rf "$test_root"' EXIT
export UPLOAD_FOLDER="$test_root/uploads"
export OUTPUT_FOLDER="$test_root/training"
python3 -m py_compile chat/app.py chat/agent_gateway.py chat/provider_store.py chat/proxy.py host-helper/ollama_control_helper.py
python3 -m unittest discover -s tests -v
for script in ollama-control agent/entrypoint.sh scripts/*.sh tests/*.sh; do bash -n "$script"; done
docker compose config --quiet
command -v node >/dev/null || { echo 'ERROR: node is required for JavaScript syntax validation' >&2; exit 1; }
for file in chat/static/*.js; do node --check "$file"; done
