# Aperyn 1.27.1

## Clean server release

- Removes the experimental desktop/Tauri client, its workflow, documentation,
  and release path. Aperyn is a web/server product again.
- Publishes the web and private Agent runtime as fresh packages owned by this
  repository: `aperyn-web` and `aperyn-agent-runtime`.

## Host SDK Runner

- Adds an opt-in, socket-activated host runner for fixed developer commands:
  .NET, Rust/Cargo, Java, GCC/G++, CMake, Make, Python/pip, Node/npm/npx,
  Go, Ruby/bundle, and PHP/composer.
- The Agent container receives only a Unix socket; it has no Docker socket,
  privileged mode, writable host root, TCP host-runner endpoint, or arbitrary
  shell/systemd API.
- The runner is non-root, uses the invoking user, and confines command working
  directories to the configured Agent workspace and `/mnt` boundary.
- Run `./ollama-control up` to repair it when needed, or
  `./ollama-control install-host-runner` explicitly.

Running project builds can execute project-defined build hooks. Keep Agent
approval mode enabled for workspaces you do not trust.
