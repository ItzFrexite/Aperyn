# Aperyn 1.27.3

- Repairs the Host Runner: it is now a persistent non-root systemd service
  owning its Unix socket, rather than relying on incompatible socket
  activation. Its path-boundary config is root-owned but readable by its
  non-root service account.
- Adds visible pencil buttons to rename saved Chat and Agent sessions, in
  addition to automatic first-prompt titles.
