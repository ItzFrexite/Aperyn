# Docker host deployment

The supported architecture is native systemd Ollama plus Dockerized Aperyn.

## Prerequisites

- Linux with Docker Engine and Docker Compose v2
- Ollama reachable at `127.0.0.1:11434`
- Optional sudo access for the one-time helper installation

## Standard launch

```bash
cp .env.example .env
docker compose up -d
```

Compose pulls `ghcr.io/itzfrexite/aperyn:latest` and `ghcr.io/itzfrexite/aperyn-agent:latest`, then starts the proxy, WebUI, and private Agent runtime without a local build. The Agent service publishes no host port.

When `APERYN_AGENT_WORKSPACE` is blank, Compose mounts the current host user's home directory as one Agent boundary. It separately mounts `APERYN_AGENT_MNT` (`/mnt` by default), so root-level mounted projects appear in the picker without exposing host `/`. Set either to an absolute safe parent when projects live elsewhere. Set `APERYN_AGENT_UID` and `APERYN_AGENT_GID` to a non-root host owner with write permission, or use `./ollama-control up` to populate these values automatically on a fresh setup. Do not mount the Docker socket, host root, or system directories.

## Host helper

For live GPU telemetry and global Ollama performance controls, run:

```bash
./ollama-control up
```

The helper binds only to loopback, accepts fixed endpoints and an explicit environment-variable allow-list, and cannot execute browser-supplied commands or arbitrary `systemctl` operations. Its stable identity is `/var/lib/ollama-control/helper.token`; no token is shipped.

Raw Compose startup remains supported when the helper is absent. The UI distinguishes not installed, installed but stopped, authentication mismatch, and unreachable states.

For an Ollama service on a different Linux machine, use the paired outbound Host Connector described in `REMOTE_HOSTS.md`; do not bind that machine's helper beyond loopback.

## Configuration and updates

Safe defaults are in `.env.example`. Keep the copied `.env` private. Common settings are `MANAGER_PORT`, `PROXY_PORT`, `OLLAMA_API`, `OLLAMA_CONTROL_IMAGE`, `APERYN_AGENT_IMAGE`, `APERYN_AGENT_WORKSPACE`, and `APERYN_AGENT_MNT`.

```bash
git pull
docker compose up -d
```

Persistent `data/`, `models/`, the Agent workspace, and `.env` remain outside the image. For HTTPS-only deployments, set `SESSION_COOKIE_SECURE=true` and forward the original scheme.
