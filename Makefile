.PHONY: help setup preflight install-helper install-host-runner uninstall-helper up down restart pull status logs test

help:
	@echo "Aperyn 1.27.8"
	@echo "  make up             Safe preflight, helper repair, and Compose startup"
	@echo "  make preflight      Validate host Ollama, Docker, ports, and helper"
	@echo "  make install-helper Install/repair the allow-listed localhost helper"
	@echo "  make install-host-runner Install/repair the non-root host SDK runner"
	@echo "  make down           Stop Aperyn (native Ollama is untouched)"
	@echo "  make status         Show container status"
	@echo "  make test           Run the 1.27.8 validation suite"

setup:
	@test -f .env || cp .env.example .env
	@mkdir -p data models

preflight:
	@bash scripts/preflight-check.sh
	@bash scripts/detect-hardware.sh || true

install-helper:
	@bash scripts/install-performance-helper.sh

install-host-runner:
	@bash scripts/install-host-runner.sh

uninstall-helper:
	@bash scripts/uninstall-performance-helper.sh

up:
	@./ollama-control up

down:
	@docker compose down

restart:
	@docker compose restart

pull:
	@docker compose pull

status:
	@docker compose ps

logs:
	@docker compose logs -f

test:
	@bash tests/run-tests.sh
