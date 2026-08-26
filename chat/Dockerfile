FROM python:3.12-slim

LABEL org.opencontainers.image.title="Aperyn" \
      org.opencontainers.image.description="An Ollama model editor and chat" \
      org.opencontainers.image.source="https://github.com/ItzFrexite/Aperyn" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# curl is used only by Docker health checks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY agent_gateway.py .
COPY provider_store.py .
COPY proxy.py .
COPY templates/ templates/
COPY static/ static/

RUN mkdir -p /tmp/uploads /data/training

EXPOSE 3000 11435

CMD ["python", "app.py"]
