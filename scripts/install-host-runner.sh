#!/usr/bin/env bash
set -euo pipefail
runner_user=${SUDO_USER:-${USER}}
workspace=${APERYN_AGENT_WORKSPACE:-/home/$runner_user}
mnt_root=${APERYN_AGENT_MNT:-/mnt}
id "$runner_user" >/dev/null
sudo install -d -m 700 -o "$runner_user" -g "$runner_user" /var/lib/aperyn-host-runner /etc/aperyn-host-runner /usr/local/lib/aperyn-host-runner
sudo install -m 755 host-runner/aperyn_host_runner.py /usr/local/lib/aperyn-host-runner/aperyn_host_runner.py
sudo install -m 644 host-runner/aperyn-host-runner.socket /etc/systemd/system/aperyn-host-runner@.socket
sudo install -m 644 host-runner/aperyn-host-runner@.service /etc/systemd/system/aperyn-host-runner@.service
runner_config=$(python3 -c 'import json,sys; print(json.dumps({"workspace_root":sys.argv[1],"mnt_root":sys.argv[2]}, indent=2))' "$workspace" "$mnt_root")
printf '%s\n' "$runner_config" | sudo tee /etc/aperyn-host-runner/config.json >/dev/null
sudo chown root:root /etc/aperyn-host-runner/config.json
sudo chmod 600 /etc/aperyn-host-runner/config.json
sudo systemctl daemon-reload
sudo systemctl enable --now "aperyn-host-runner@${runner_user}.socket"
echo "Aperyn Host Runner is ready for ${runner_user}; it is non-root and limited to ${workspace} and ${mnt_root}."
