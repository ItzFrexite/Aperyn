FROM ghcr.io/anomalyco/opencode:1.18.17@sha256:c472d1c6c575b86ccc44ff639a1bb2093fd75ab7095be46f8b3c0a04c299fd60

LABEL org.opencontainers.image.title="Aperyn Agent Runtime" \
      org.opencontainers.image.description="Pinned OpenCode runtime for Aperyn's private agent service" \
      org.opencontainers.image.source="https://github.com/ItzFrexite/Aperyn" \
      org.opencontainers.image.licenses="MIT"

USER root
RUN apk add --no-cache bash ca-certificates git jq openssh-client ripgrep su-exec python3 py3-pip \
    && pip3 install --no-cache-dir --break-system-packages python-pptx python-docx openpyxl

COPY entrypoint.sh /usr/local/bin/aperyn-agent-entrypoint
COPY host-tool /usr/local/lib/aperyn-host-tool
COPY OPENCODE_LICENSE /licenses/OpenCode-LICENSE
RUN chmod 0755 /usr/local/bin/aperyn-agent-entrypoint /usr/local/lib/aperyn-host-tool \
    && for tool in dotnet cargo rustc java javac gcc g++ cmake make; do ln -s /usr/local/lib/aperyn-host-tool "/usr/local/bin/$tool"; done

ENV HOME=/agent-data/home \
    XDG_DATA_HOME=/agent-data/xdg-data \
    XDG_CONFIG_HOME=/agent-data/xdg-config \
    OPENCODE_CONFIG=/agent-data/opencode.json \
    OPENCODE_CONFIG_DIR=/agent-data/config \
    OPENCODE_DISABLE_AUTOUPDATE=1 \
    OPENCODE_DISABLE_PRUNE=1

ENTRYPOINT ["/usr/local/bin/aperyn-agent-entrypoint"]
CMD ["serve", "--hostname", "0.0.0.0", "--port", "4096"]
