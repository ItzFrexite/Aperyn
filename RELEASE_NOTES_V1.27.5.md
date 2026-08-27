# Aperyn 1.27.5

- Fixes the Host Runner client when it is invoked from the Agent image's own
  working directory: fixed developer-tool calls now safely use the configured
  `/workspace` mapping instead of failing before the host command runs.
- Makes the non-root Host Runner a normal boot-persistent systemd service and
  updates `./ollama-control up` to detect/repair that service automatically.
- Removes the harmless obsolete-socket systemd warning during Host Runner
  repair.
- Centres the compact mobile Activity arrow precisely inside its button.
