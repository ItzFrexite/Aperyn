# Aperyn 1.27.7

- Fixes Agent workspace browsing for autofs/CIFS-mounted folders such as
  `/mnt/nas/code`. One-way mount propagation keeps late-mounted NAS subfolders
  visible inside the WebUI and Agent containers without propagating changes
  back to the host.
- Makes the Ask first, Auto safe, and Full control approval selector available
  in mobile portrait, with compact controls that fit beside the model chooser.
