#!/usr/bin/env bash
set -euo pipefail
runner_user=${SUDO_USER:-${USER}}
# Read only the two non-secret workspace boundaries from a local .env when it
# exists. Do not source .env: it can contain connection credentials.
env_value() { grep -E "^$1=" .env 2>/dev/null | tail -n 1 | cut -d= -f2- || true; }
workspace=${APERYN_AGENT_WORKSPACE:-$(env_value APERYN_AGENT_WORKSPACE)}
mnt_root=${APERYN_AGENT_MNT:-$(env_value APERYN_AGENT_MNT)}
workspace=${workspace:-/home/$runner_user}
mnt_root=${mnt_root:-/mnt}
id "$runner_user" >/dev/null
sudo install -d -m 700 -o "$runner_user" -g "$runner_user" /var/lib/aperyn-host-runner
# The boundary configuration contains no credential. The non-root service
# needs directory traversal to read its root-owned, read-only config file.
sudo install -d -m 755 -o root -g root /etc/aperyn-host-runner
sudo install -d -m 755 -o root -g root /usr/local/lib/aperyn-host-runner
sudo install -m 755 host-runner/aperyn_host_runner.py /usr/local/lib/aperyn-host-runner/aperyn_host_runner.py
sudo install -m 644 host-runner/aperyn-host-runner@.service /etc/systemd/system/aperyn-host-runner@.service
runner_config=$(python3 -c 'import json,sys; print(json.dumps({"workspace_root":sys.argv[1],"mnt_root":sys.argv[2]}, indent=2))' "$workspace" "$mnt_root")
printf '%s\n' "$runner_config" | sudo tee /etc/aperyn-host-runner/config.json >/dev/null
sudo chown root:root /etc/aperyn-host-runner/config.json
# This file only records non-secret path boundaries; the service user must be
# able to read it, while the root-owned directory prevents modification.
sudo chmod 644 /etc/aperyn-host-runner/config.json
sudo systemctl disable --now "aperyn-host-runner@${runner_user}.socket" 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl reset-failed "aperyn-host-runner@${runner_user}.service" || true
sudo systemctl enable --now "aperyn-host-runner@${runner_user}.service"
echo "Aperyn Host Runner is ready for ${runner_user}; it is non-root and limited to ${workspace} and ${mnt_root}."
