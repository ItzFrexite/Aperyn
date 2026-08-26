#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then cp .env.example .env; fi
TOKEN_FILE=/var/lib/ollama-control/helper.token
sudo install -d -m 700 /var/lib/ollama-control
if sudo test -s "$TOKEN_FILE"; then
  TOKEN=$(sudo cat "$TOKEN_FILE")
else
  if command -v openssl >/dev/null 2>&1; then TOKEN=$(openssl rand -hex 32); else TOKEN=$(python3 - <<'PY'
import secrets; print(secrets.token_hex(32))
PY
); fi
  printf '%s\n' "$TOKEN" | sudo tee "$TOKEN_FILE" >/dev/null
  sudo chmod 600 "$TOKEN_FILE"
fi
python3 - "$TOKEN" <<'PY2'
from pathlib import Path
import sys
p=Path('.env'); token=sys.argv[1]; lines=p.read_text().splitlines(); out=[]; found=False
for line in lines:
    if line.startswith('OLLAMA_CONTROL_HELPER_TOKEN='):
        if not found: out.append('OLLAMA_CONTROL_HELPER_TOKEN='+token); found=True
    else: out.append(line)
if not found: out += ['', '# Shared secret for the localhost-only privileged performance helper.', 'OLLAMA_CONTROL_HELPER_TOKEN='+token]
p.write_text('\n'.join(out)+'\n')
PY2
TMP=$(mktemp)
printf 'OLLAMA_CONTROL_HELPER_TOKEN_FILE=%s\nOLLAMA_CONTROL_HELPER_PORT=11436\nOLLAMA_CONTROL_OLLAMA_SERVICE=ollama\n' "$TOKEN_FILE" > "$TMP"
echo "Installing localhost-only Ollama performance helper..."

# nvtop is useful for interactive host monitoring. Aperyn does not scrape
# its ncurses screen; the helper reads stable NVIDIA/AMD telemetry sources directly.
# Install nvtop best-effort so administrators also have a terminal GPU monitor.
if ! command -v nvtop >/dev/null 2>&1; then
  echo "nvtop not found; attempting a best-effort package install..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq || true
    sudo apt-get install -y nvtop || echo "Warning: nvtop package install failed; live helper telemetry can still work via driver tools/sysfs."
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y nvtop || echo "Warning: nvtop package install failed; continuing."
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm nvtop || echo "Warning: nvtop package install failed; continuing."
  else
    echo "No supported package manager found for automatic nvtop installation; continuing without it."
  fi
fi
sudo install -d -m 755 /usr/local/lib/ollama-control /etc/ollama-control
sudo install -m 755 host-helper/ollama_control_helper.py /usr/local/lib/ollama-control/ollama_control_helper.py
sudo install -m 644 host-helper/ollama-control-helper.service /etc/systemd/system/ollama-control-helper.service
sudo install -m 600 "$TMP" /etc/ollama-control/helper.env
rm -f "$TMP"
sudo systemctl daemon-reload
sudo systemctl enable --now ollama-control-helper
printf 'Helper status: '
curl -fsS http://127.0.0.1:11436/v1/ping >/dev/null && echo OK || echo FAILED
echo "Persistent helper identity: $TOKEN_FILE"
echo "Restart Aperyn so containers receive the synchronized token: ./ollama-control up"
