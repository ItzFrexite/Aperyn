# Security

Do not include passwords, tokens, prompts, databases, attachments, logs, domains, or machine details in reports or releases. Report vulnerabilities privately through the repository's GitHub Security Advisory interface when available; do not open a public issue containing exploit or deployment details.

## Authentication

WebUI routes require local SQLite accounts. Passwords use Werkzeug scrypt. A fresh empty database creates `admin` / `password` only at runtime and forces replacement; releases contain no database or hash. Existing accounts are never reset.

Sessions use a persistent random secret, HttpOnly cookies, SameSite=Lax, configurable/detected Secure cookies, CSRF validation, and login backoff. The final active administrator is protected.

## Trust boundaries

The 11435 proxy is not covered by WebUI login in 1.27.1; restrict it by firewall. The helper binds to loopback, uses a host-persistent token, exposes fixed routes, and allow-lists every setting. The WebUI has no Docker socket, privileged mode, writable host root, arbitrary shell, or generic systemd control.

Agent is administrator-only. Its OpenCode service has no published port and receives a persistent generated Basic Auth password from `data/agent/server.password`; that credential is read only by the server-side gateway. The Agent container has `no-new-privileges`, runs tasks as the configured non-root UID/GID, and can access only its data volume plus two explicit trees: `APERYN_AGENT_WORKSPACE` (the Compose user's home directory when blank) and `APERYN_AGENT_MNT` (`/mnt` by default). The WebUI receives both boundaries read-only for folder discovery; only Agent receives writable mounts. No host-root or Docker-socket mount is used. The picker resolves every selection beneath one of those roots and rejects traversal, external absolute paths, symlinks, files, and unreadable folders. The canonical launcher refuses `/` as a boundary. OpenCode read rules deny common credential locations (`.ssh`, `.gnupg`, `.aws`, `.kube`, Docker/GitHub CLI configuration and credential dotfiles) plus environment files. Directory listing, navigation, and `git status` are pre-approved; file edits, writes, subtasks, network tools, and all other shell commands ask by default. External-directory access remains denied. Mount only parent directories you intentionally authorize and review approvals carefully.

External provider credentials are server-wide and administrator-managed. SQLite values are encrypted with a persistent Fernet key stored as `data/provider-secrets.key`. Agent receives separate `0600` runtime key files under `data/agent/providers/`; neither location is included in releases. API responses expose only masked connection state. Provider calls are limited to the official OpenAI, Anthropic, and Google Gemini HTTPS endpoints to avoid an administrator-configurable server-side request proxy.

Dashboard telemetry deletion is administrator-only and CSRF-protected. Clearing the proxy's completed live summaries uses a purpose-specific HMAC derived from the persistent session secret; the session secret itself is never transmitted. The identity is compared in constant time and is never returned to the browser. Active generation records are preserved.

Generated previews use sandboxed iframes. Telemetry excludes prompt and response bodies by default.

## Release hygiene

Run `tests/release-audit.sh PATH_TO_ZIP`. Releases exclude `.env`, `data/`, databases, uploads, logs, tokens, session secrets, caches, dependencies, VCS metadata, and local identifiers.
