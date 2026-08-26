# Aperyn 1.27.0

## Clean web/server release

- Removes the experimental Windows desktop/Tauri application, its build
  workflow, documentation, and tests. Aperyn is again a focused Docker WebUI
  and telemetry proxy.
- Starts the new public GitHub repository with no desktop application history.

## Host SDK Runner

- Adds a non-root, systemd socket-activated Host Runner for Agent SDK commands.
- Supports a fixed tool allow-list including `dotnet`, Node/npm, Cargo/Rust,
  Java, GCC/G++, CMake, Make, and Python.
- Maps only the configured Agent workspace and `/mnt` boundary from the
  container to the host; commands cannot escape either boundary.
- Does not expose a TCP port, Docker socket, host root mount, arbitrary shell,
  or root execution path.
- `./ollama-control up` repairs the Host Runner when required; use
  `./ollama-control install-host-runner` explicitly if preferred.
