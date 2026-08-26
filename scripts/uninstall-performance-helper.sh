#!/usr/bin/env bash
set -euo pipefail
sudo systemctl disable --now ollama-control-helper 2>/dev/null || true
sudo rm -f /etc/systemd/system/ollama-control-helper.service
sudo rm -rf /usr/local/lib/ollama-control /etc/ollama-control
# Keep /var/lib/ollama-control/helper.token by default so a reinstall retains identity.
# Deliberately keep 95-ollama-control.conf so removing the UI helper cannot silently change Ollama tuning.
sudo systemctl daemon-reload
echo 'Helper removed. Existing Aperyn performance drop-in was left in place.'
