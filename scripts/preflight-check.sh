#!/usr/bin/env bash
# Pre-flight checks for the default Linux host-Ollama deployment.
set -u

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ERRORS=0; WARNINGS=0
MANAGER_PORT=15736; PROXY_PORT=11435; OLLAMA_API=http://127.0.0.1:11434
if [ -f ./.env ]; then
  v=$(grep -E '^MANAGER_PORT=' ./.env | tail -n1 | cut -d= -f2- | tr -d '[:space:]"\047' || true); [[ "$v" =~ ^[0-9]+$ ]] && MANAGER_PORT="$v"
  v=$(grep -E '^PROXY_PORT=' ./.env | tail -n1 | cut -d= -f2- | tr -d '[:space:]"\047' || true); [[ "$v" =~ ^[0-9]+$ ]] && PROXY_PORT="$v"
  v=$(grep -E '^OLLAMA_API=' ./.env | tail -n1 | cut -d= -f2- | tr -d '[:space:]"\047' || true); [ -n "$v" ] && OLLAMA_API="$v"
fi

echo -e "${BLUE}Aperyn - host deployment pre-flight${NC}"
echo

printf 'Docker CLI... '
if command -v docker >/dev/null 2>&1; then echo -e "${GREEN}OK${NC}"; else echo -e "${RED}MISSING${NC}"; ERRORS=$((ERRORS+1)); fi
printf 'Docker daemon... '
if docker info >/dev/null 2>&1; then echo -e "${GREEN}OK${NC}"; else echo -e "${RED}NOT RUNNING / NO ACCESS${NC}"; ERRORS=$((ERRORS+1)); fi
printf 'Docker Compose v2... '
if docker compose version >/dev/null 2>&1; then echo -e "${GREEN}OK${NC}"; else echo -e "${RED}MISSING${NC}"; ERRORS=$((ERRORS+1)); fi
printf 'Host Ollama API... '
if curl -fsS --max-time 4 "$OLLAMA_API/api/version" >/dev/null 2>&1; then echo -e "${GREEN}OK ($OLLAMA_API)${NC}"; else echo -e "${RED}UNREACHABLE ($OLLAMA_API)${NC}"; ERRORS=$((ERRORS+1)); fi

port_in_use() {
  local p="$1"
  if command -v ss >/dev/null 2>&1; then ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$p$"; return; fi
  if command -v lsof >/dev/null 2>&1; then lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; return; fi
  return 1
}

printf 'Dashboard port %s... ' "$MANAGER_PORT"
if port_in_use "$MANAGER_PORT"; then echo -e "${YELLOW}IN USE${NC}"; WARNINGS=$((WARNINGS+1)); else echo -e "${GREEN}AVAILABLE${NC}"; fi
printf 'Proxy port %s... ' "$PROXY_PORT"
if port_in_use "$PROXY_PORT"; then echo -e "${YELLOW}IN USE${NC}"; WARNINGS=$((WARNINGS+1)); else echo -e "${GREEN}AVAILABLE${NC}"; fi

printf 'Performance helper... '
if curl -fsS --max-time 2 http://127.0.0.1:11436/v1/ping >/dev/null 2>&1; then
  echo -e "${GREEN}INSTALLED${NC}"
else
  echo -e "${BLUE}optional / not installed (run make install-helper for global tuning)${NC}"
fi

printf 'Host GPU probe... '
GPU_NOTE=''
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  GPU_NOTE='NVIDIA via nvidia-smi'
elif compgen -G '/sys/class/drm/card[0-9]*/device/mem_info_vram_total' >/dev/null 2>&1 || compgen -G '/sys/class/drm/card[0-9]*/device/lmem_total_bytes' >/dev/null 2>&1; then
  GPU_NOTE='DRM/sysfs VRAM'
elif command -v rocm-smi >/dev/null 2>&1 && rocm-smi --showmeminfo vram >/dev/null 2>&1; then
  GPU_NOTE='AMD via rocm-smi'
fi
if [ -n "$GPU_NOTE" ]; then echo -e "${GREEN}DETECTED ($GPU_NOTE)${NC}"; else echo -e "${BLUE}not directly detected; hardware snapshot will try Ollama journal fallback${NC}"; fi

# The richer hardware snapshot is written immediately after this check by the Makefile.

echo
if [ "$ERRORS" -gt 0 ]; then
  echo -e "${RED}$ERRORS blocking issue(s), $WARNINGS warning(s).${NC}"
  exit 1
fi
if [ "$WARNINGS" -gt 0 ]; then
  echo -e "${YELLOW}Checks passed with $WARNINGS warning(s). Change MANAGER_PORT/PROXY_PORT in .env if needed.${NC}"
else
  echo -e "${GREEN}All checks passed.${NC}"
fi
echo "Next: cp .env.example .env && docker compose up -d"
echo "Dashboard: http://localhost:$MANAGER_PORT"
echo "Client API: http://localhost:$PROXY_PORT"
