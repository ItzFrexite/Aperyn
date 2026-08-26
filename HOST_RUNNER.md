# Aperyn Host Runner

The Host Runner lets Agent use host-installed SDKs such as `dotnet`, Cargo,
Java, GCC and CMake without privileging the Agent container.

It is a non-root, systemd socket service. The Agent reaches it only through a
private Unix socket. There is no TCP listener, Docker socket, host root mount,
generic shell endpoint, or root command execution.

Only fixed executable names and structured arguments are accepted. `/workspace`
and `/mnt` are mapped to the configured host boundaries and path escapes are
rejected. Agent's Node/Python runtime stays inside the container so OpenCode
continues to operate normally.

Install it with:

```bash
./ollama-control install-host-runner
```

`./ollama-control up` installs or repairs it if absent. Host SDK builds can run
project build scripts, so keep Agent approvals enabled for untrusted work.
