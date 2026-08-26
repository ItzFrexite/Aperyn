# Managed remote Ollama hosts

Aperyn can use an Ollama endpoint on another machine for Chat, Agent and model management. To also view that machine's GPU telemetry or change its global Ollama settings, pair an **Aperyn Host Connector** on that same machine.

## Security model

The remote machine keeps native Ollama and the privileged helper bound to loopback (`127.0.0.1`). The connector makes an authenticated outbound HTTPS connection to Aperyn; it does not listen on a network port and does not expose the helper, Docker socket, root filesystem, or arbitrary shell execution.

The server stores only hashes of connector credentials. A pairing token is shown once, expires after 15 minutes, and is exchanged for a new connector credential stored with `0600` permissions on the remote host.

The connector accepts only these fixed operations:

- read helper status;
- read helper GPU telemetry;
- apply the helper's existing allow-listed global Ollama settings.

It cannot run arbitrary commands or choose arbitrary systemd units.

## Pair a host

1. On the remote Linux machine, install native Ollama and the normal localhost-only Aperyn performance helper first.
2. In Aperyn **Settings → Managed Ollama hosts**, add the machine's Ollama endpoint and select **Pair connector**.
3. Copy the displayed one-time command and run it from the extracted Aperyn release directory on the remote machine. It installs and starts the `aperyn-host-connector` systemd service.
4. Select **Use host** in Aperyn. Chat, Model Library, installed-model management and Agent now target that Ollama endpoint; global performance tuning and hardware information come from the paired connector.

The server must be reachable from the remote host over HTTPS. `localhost` is permitted only for development/testing. A VPN or private HTTPS endpoint is recommended; never publish the native Ollama or helper loopback ports merely for this integration.

## Disconnecting

Removing a managed host in Settings revokes its server credential immediately. On the remote host, optionally run:

```bash
sudo systemctl disable --now aperyn-host-connector
sudo rm -rf /etc/aperyn-host-connector
```

This does not alter Ollama or the existing local performance helper.
