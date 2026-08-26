# Aperyn Host Runner

The Host Runner lets Agent use host-installed SDKs such as `dotnet`, Python,
Node/npm, Cargo, Java, GCC and CMake without privileging the Agent container.

It is a non-root, systemd socket service. The Agent reaches it only through a
private Unix socket. There is no TCP listener, Docker socket, host root mount,
generic shell endpoint, or root command execution.

Only fixed executable names and structured arguments are accepted. `/workspace`
and `/mnt` are mapped to the configured host boundaries and path escapes are
rejected. The allow-list covers .NET, Python/pip, Node/npm/npx, Rust/Cargo,
Java, GCC/G++, CMake, Make, Go, Ruby/bundle and PHP/composer. Each command
resolves from the normal Ubuntu user environment.

Install it with:

```bash
./ollama-control install-host-runner
```

`./ollama-control up` installs or repairs it if absent. Host SDK builds can run
project build scripts, so keep Agent approvals enabled for untrusted work.
