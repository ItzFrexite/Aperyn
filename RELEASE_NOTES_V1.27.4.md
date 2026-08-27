# Aperyn 1.27.4

- Repairs the final Host Runner permission boundary: the non-secret,
  root-owned configuration directory is now traversable by the configured
  non-root service user, while the configuration remains root-owned and
  read-only.
