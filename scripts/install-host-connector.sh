#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <https://aperyn-server-or-private-http-url> <host-id> <one-time-pairing-token>" >&2
  exit 2
fi
SERVER_URL=$1
HOST_ID=$2
PAIR_TOKEN=$3
case "$SERVER_URL" in https://*|http://*) ;; *) echo 'Server URL must use http:// or https://.' >&2; exit 2;; esac
sudo install -d -m 700 /etc/aperyn-host-connector /usr/local/lib/aperyn-host-connector
sudo install -m 755 host-connector/aperyn_host_connector.py /usr/local/lib/aperyn-host-connector/aperyn_host_connector.py
sudo /usr/bin/python3 /usr/local/lib/aperyn-host-connector/aperyn_host_connector.py --config /etc/aperyn-host-connector/config.json pair --server-url "$SERVER_URL" --host-id "$HOST_ID" --pairing-token "$PAIR_TOKEN"
sudo install -m 644 host-connector/aperyn-host-connector.service /etc/systemd/system/aperyn-host-connector.service
sudo systemctl daemon-reload
sudo systemctl enable --now aperyn-host-connector
echo 'Aperyn Host Connector paired and running. It makes an outbound authenticated connection only.'
