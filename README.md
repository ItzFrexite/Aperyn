# Aperyn

**An Ollama model editor and chat.** Meet **Nym**, Aperyn's signal-moth assistant.

Aperyn is a self-hosted control plane for a native Ollama service. It combines an authenticated multi-user WebUI, chat workspace, model operations, hardware-aware estimates, downloads, storage tools, and a transparent telemetry proxy without putting Ollama itself in Docker.

## Architecture

```text
clients -> :11435 transparent proxy -> 127.0.0.1:11434 native Ollama
browser -> :15736 Docker WebUI -> proxy / persistent SQLite data
WebUI -> private Agent sidecar -> explicit host workspace + :11435 proxy
host launcher -> localhost:11436 allow-listed systemd helper
```

The WebUI maps host port **15736** to container port **3000**. Clients such as Aider, Continue, and OpenCode should use `http://your-server:11435`. Native Ollama remains private on `127.0.0.1:11434` by default.

## Install from GitHub

Prerequisites: Linux, Docker Engine with Compose v2, and native Ollama responding on `127.0.0.1:11434`.

```bash
git clone https://github.com/ItzFrexite/Aperyn.git
cd Aperyn
cp .env.example .env
docker compose up -d
```

Compose pulls `ghcr.io/itzfrexite/aperyn:latest`; no local application build is required. Open `http://your-server:15736`. A fresh database starts with `admin` / `password` and requires an immediate password change.

For live GPU telemetry and safe global Ollama tuning, use the host launcher once:

```bash
./ollama-control up
```

It asks for sudo only when it must install or repair the localhost-only, allow-listed helper. Raw `docker compose up -d` remains safe without it; Settings reports the precise helper state and installation command.

## Remote Ollama hosts

Chat, Agent and model operations can use a configured remote Ollama endpoint through Aperyn's proxy. For remote GPU telemetry and safe global Ollama tuning, pair the outbound **Aperyn Host Connector** on that remote Linux machine. It keeps Ollama and the allow-listed helper on loopback and opens no inbound control port. See [REMOTE_HOSTS.md](REMOTE_HOSTS.md).

## Host SDK Runner

Agent can use selected developer SDKs installed on its Linux host without
privileging the container. The non-root, Unix-socket-only **Aperyn Host Runner**
maps Agent workspace paths to the configured host workspace and exposes a fixed
tool allow-list. See [HOST_RUNNER.md](HOST_RUNNER.md).

## Configuration

The committed `.env.example` contains safe defaults. Copy it to `.env` before customizing ports or optional tokens. `.env` is ignored by Git and must never be committed.

Important settings include:

- `MANAGER_PORT=15736` — WebUI host port.
- `PROXY_PORT=11435` — Ollama-compatible telemetry proxy.
- `OLLAMA_API=http://127.0.0.1:11434` — native Ollama upstream.
- `OLLAMA_CONTROL_IMAGE=ghcr.io/itzfrexite/aperyn:latest` — published image; replace `latest` with a release version to pin it.
- `APERYN_AGENT_IMAGE=ghcr.io/itzfrexite/aperyn-agent:latest` — private headless Agent runtime image; pin it alongside the WebUI.
- `APERYN_AGENT_WORKSPACE=` — optional host-folder boundary. Blank uses the Compose user's home directory, so Agent can browse normal project folders. Set an absolute safe parent for another disk; never use `/` or a directory containing `docker.sock`.
- `APERYN_AGENT_MNT=/mnt` — second explicit picker root for root-level mounted storage. This grants Agent access to that tree only; it does not mount host `/`.
- `APERYN_AGENT_CONTEXT_LIMIT=98304` — server-wide Agent context target. Choose 4096–1048576; Aperyn clamps it to the selected model's declared architecture maximum on the next `docker compose up -d`.
- `APERYN_AGENT_UID` / `APERYN_AGENT_GID` — non-root identity that must be able to write the workspace; `./ollama-control up` fills these from the current host user on a fresh setup.
- `HF_TOKEN=` — optional access to gated Hugging Face repositories.
- `SESSION_COOKIE_SECURE=true` — use when the WebUI is served exclusively through HTTPS.

## Updates

Mutable state stays outside the image in `./data/`; model imports remain under `./models/`, and Agent projects remain in the configured workspace. Keep these directories and `.env` across updates.

```bash
git pull
docker compose up -d
```

`pull_policy: always` makes Compose check GHCR for the selected tag. To make the pull explicit, run `docker compose pull` first. Database migrations preserve users, password hashes, themes, chats, telemetry, preferences, and settings.

## Publishing and development

Pushes to `main` run the validation suite and publish the multi-architecture `latest` image to GHCR. Tags such as `v1.27.0` also publish immutable version tags. Pull requests run tests without publishing.

The GitHub Actions workflow uses the repository-scoped `GITHUB_TOKEN` with `contents: read` and `packages: write`. It publishes the WebUI/proxy image and the pinned private Agent runtime image; normal users only pull them.

## Agent

The private Agent runtime includes Python with `python-pptx`, `python-docx`,
and `openpyxl`, so an approved Agent task can create PowerPoint, Word, and
Excel files in its selected working directory. These files remain inside the
configured workspace boundary; do not ask Chat to execute arbitrary model
output in the WebUI container.

Agent is a persistent coding-task workspace for administrators. Its folder picker exposes two deliberate roots: the Docker Compose user's home directory and root-level `/mnt` (configurable with `APERYN_AGENT_MNT`). Set `APERYN_AGENT_WORKSPACE` to change the home-side boundary. Containment checks reject traversal and symlink escapes, and each saved session remembers its folder; browser selection cannot broaden either configured boundary.

`~/mnt/project` means `/home/your-user/mnt/project`; `/mnt/project` is the separate root-level mounted-storage tree. The picker shows `/mnt` at the top of the home view so either can be chosen without exposing the rest of the host filesystem.

Agent uses enabled local or external models, saves an ownership mapping in SQLite, and polls the private engine for the complete message/tool timeline. Closing the browser does not abort an active task; returning from the same or another device restores the server-side session, todos, diffs, approvals, and questions. Session badges distinguish running, waiting for approval, completed, stopped, and failed tasks. While a task runs, an empty composer shows Stop; typing changes it back to Send and queues the follow-up. A host or container restart preserves session history but can interrupt the command running at that instant.

While Agent is active, Nym shows an in-timeline working state and the current reasoning disclosure opens as OpenCode supplies partial thinking updates. Fenced code blocks in both Chat and Agent use Aperyn's local language detector and Visual Studio-inspired syntax palette; code never leaves the configured inference/provider path for highlighting.

The Agent top bar includes an OpenCode-derived context tracker. It uses OpenCode's latest non-zero `tokens.total` counter (falling back to input + cache-read + output) and compares it with OpenCode's `model.limit.context`. A just-started streaming message cannot temporarily reset an established session to 0%. Aperyn supplies local Ollama limits from `/api/show` model metadata; external models use the limits reported by their OpenCode provider. If no trustworthy limit exists, the interface reports it as unavailable instead of displaying a false percentage.

When a task changes files, Agent attaches a review card to the response that produced those changes and mirrors the session-wide total in Activity. Both show total and per-file additions/deletions; selecting a filename opens a responsive viewer with old/new line numbers, green additions, and red removals. Aperyn renders structured change data already returned by the private OpenCode session API and does not expose an additional arbitrary file-reading endpoint.

In non-Git workspaces, OpenCode may return an empty session diff even after its structured write tool creates a file. Aperyn recovers those completed write/edit records from the saved session timeline, rejects paths outside that session's workspace, and never infers changes from arbitrary shell output.

Thinking disclosures in both Chat and Agent retain the state chosen by the user while streamed or polled content updates. Switching to another conversation starts with that conversation's own disclosure state.

Ordinary directory listing and navigation commands are pre-approved. The composer offers **Ask first**, **Auto safe** (routine inspection only), and **Full control** for the selected session. Even Full control remains inside the configured non-root workspace mounts: it does not grant a Docker socket, host-root filesystem, or arbitrary systemd access. Browser notifications can alert an open/background tab or installed PWA when Nym needs approval or completes; closed-app push notifications are intentionally not enabled.

Agent is powered by OpenCode as a headless MIT-licensed engine. Aperyn supplies its own interface and authenticated gateway. OpenCode is not exposed on a host port and its credential is never sent to the browser.

## External AI connections

Administrators can connect OpenAI, Anthropic, and Google Gemini under **Settings → External model providers**. Enter an API key, use **Test & discover**, review the returned model IDs, and save only the models you want shown in Chat and Agent. A ChatGPT browser subscription/sign-in is not an OpenAI API credential, so Aperyn deliberately does not scrape browser sessions or impersonate a ChatGPT login.

Provider records are encrypted in SQLite with a persistent key generated under `data/`. Browsers receive masked state only. The Agent runtime uses separate `0600` key files under `data/agent/providers/`; these are runtime data and must never be committed. Aperyn uses fixed official HTTPS endpoints rather than accepting arbitrary provider URLs.

External Chat currently supports text conversations. Image attachments remain available through compatible local Ollama vision models.

## Security and privacy

All WebUI pages require a local account. Sessions use a persistent random secret, HttpOnly/SameSite=Lax cookies, optional Secure cookies, CSRF protection, scrypt password hashes, and login backoff. The proxy on port 11435 is separate from WebUI authentication; protect it with your firewall.

Telemetry stores operational metadata and token counts, not prompt or response bodies by default. Generated HTML/SVG previews remain sandboxed. Aperyn has no Docker socket, writable host-root mount, privileged container, arbitrary command endpoint, or generic systemd control.

Administrators can clear Dashboard request history and completed live summaries from the data-controls section at the bottom of Dashboard. The action is confirmed, CSRF-protected, and deliberately leaves active generations, chats, accounts, themes, models, settings, and Agent sessions untouched.

Never commit `.env`, `data/`, databases, attachments, logs, helper tokens, session secrets, or other runtime state. See `SECURITY.md`.

## Credits and provenance

Aperyn evolved from the MIT-licensed [manzolo/ollama-model-train-guide](https://github.com/manzolo/ollama-model-train-guide). Its required copyright and permission notice remains in `LICENSE`; substantial inherited areas were rewritten and the remaining lineage is documented in `PROVENANCE.md`.

[ollama-admin/ollama-admin](https://github.com/ollama-admin/ollama-admin) was used as a functional reference during later product development. The provenance audit found no implementation reuse from that project.

The Aperyn name, Nym mascot branding, current interface, authentication, telemetry, host-helper design, and other project-specific work are documented in `BRAND.md` and `PROVENANCE.md`. The project does not claim that every historical line was written from scratch.

## Documentation

- `START_HERE.md` — concise installation and first-login guide.
- `DOCKER_HOST_TUTORIAL.md` — native Ollama and helper architecture.
- `SECURITY.md` — security and disclosure model.
- `PROVENANCE.md` — inherited, modified, and newly written areas.
- `BRAND.md` — Aperyn’s visual system and marks.

## License

Distributed under the retained MIT licence in `LICENSE`, including its required upstream notice.
