#!/usr/bin/env bash
set -u

MANAGER_PORT="15736"
PROXY_PORT="11435"
if [ -f ./.env ]; then
  v=$(grep -E '^MANAGER_PORT=' ./.env | tail -n1 | cut -d= -f2- | tr -d '[:space:]"\047' || true); [[ "$v" =~ ^[0-9]+$ ]] && MANAGER_PORT="$v"
  v=$(grep -E '^PROXY_PORT=' ./.env | tail -n1 | cut -d= -f2- | tr -d '[:space:]"\047' || true); [[ "$v" =~ ^[0-9]+$ ]] && PROXY_PORT="$v"
fi

check() {
  local label="$1" url="$2"
  printf '%-28s ' "$label"
  if curl -fsS --max-time 5 "$url" >/tmp/ollama-control-check.$$ 2>/dev/null; then
    echo "OK"
  else
    echo "FAILED ($url)"
    return 1
  fi
}

rc=0
check "Host Ollama :11434" "http://127.0.0.1:11434/api/version" || rc=1
check "Telemetry proxy :$PROXY_PORT" "http://127.0.0.1:${PROXY_PORT}/api/version" || rc=1
check "Proxy health" "http://127.0.0.1:${PROXY_PORT}/__ollama_control/health" || rc=1
check "Dashboard :$MANAGER_PORT" "http://127.0.0.1:${MANAGER_PORT}/health" || rc=1
rm -f /tmp/ollama-control-check.$$
exit "$rc"
