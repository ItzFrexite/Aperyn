# Aperyn operational contract

Ollama is native and loopback-only on port 11434. Aperyn exposes a compatible telemetry proxy on 11435 and authenticated WebUI on host port 15736. Mutable state belongs in `data/`; source releases and images must not contain it. Use `./ollama-control up` for helper-aware startup and `README.md` for the complete architecture.
