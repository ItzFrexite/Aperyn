# Start here — Aperyn 1.27.8

Release details: `RELEASE_NOTES_V1.27.8.md`.

## Install

Install and start Ollama natively so `curl http://127.0.0.1:11434/api/version` succeeds, then:

```bash
git clone https://github.com/ItzFrexite/Aperyn.git
cd Aperyn
cp .env.example .env
docker compose up -d
```

Compose pulls the published GHCR image; it does not build locally. Open `http://your-server:15736`, sign in with the fresh-install `admin` / `password`, and replace that temporary password immediately.

If Ollama runs on another Linux machine, add it in **Settings → Managed Ollama hosts**. Pairing the outbound connector on that machine enables its safe global tuning and live GPU telemetry without exposing its helper port; see `REMOTE_HOSTS.md`.

Agent's picker exposes the Docker Compose user's home directory and root-level `/mnt` as separate explicit boundaries. Set `APERYN_AGENT_WORKSPACE` or `APERYN_AGENT_MNT` to change them, and set `APERYN_AGENT_UID` / `APERYN_AGENT_GID` to their non-root owner. `APERYN_AGENT_CONTEXT_LIMIT=98304` is the default Agent context target; change it in `.env` and run `docker compose up -d` to apply it. Do not use `/`, a system directory, or a directory containing `docker.sock`; the picker cannot cross either configured boundary.

After login, administrators can optionally connect OpenAI, Anthropic, or Google Gemini in Settings. Test the key, review the discovered model IDs, and save the desired allow-list. Keys remain in persistent runtime data and are never included in source releases.

Run `./ollama-control up` instead when installing or reconnecting the optional allow-listed host helper. It requests sudo only for that host-level operation.

## Persistent files

Keep `.env`, `data/`, `models/`, and your configured Agent workspace across updates. The database, chats, users, password hashes, themes, telemetry, preferences, generated Agent credential, and session secret are runtime data and must never be committed. The helper token remains host-owned at `/var/lib/ollama-control/helper.token`.

## Endpoints

- WebUI: `http://your-server:15736`
- Client/telemetry proxy: `http://your-server:11435`
- Native private Ollama: `http://127.0.0.1:11434`
- Optional allow-listed helper: `http://127.0.0.1:11436`

## Update

```bash
git pull
docker compose up -d
```

Compose checks GHCR for the selected image tag and database migrations run automatically without replacing persistent data.
