.PHONY: help init fireform build up up-native down logs logs-app logs-ollama shell pull-model test clean super-clean

# Bundled Ollama is gated behind a compose profile. COMPOSE includes it by
# default so every standard target runs the full in-Docker stack unchanged.
# COMPOSE_NATIVE omits it for running Ollama natively on the host (see up-native).
COMPOSE        = docker compose -f docker/dev/compose.yml --env-file docker/.env.dev --profile bundled-ollama
COMPOSE_NATIVE = docker compose -f docker/dev/compose.yml --env-file docker/.env.dev
ENV_DEV        = docker/.env.dev

# Read OLLAMA_MODEL from .env.dev at runtime; fall back to default if file absent.
OLLAMA_MODEL = $(shell grep -E '^OLLAMA_MODEL=' $(ENV_DEV) 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || echo qwen2.5:1.5b)

help:
	@printf '%s\n' \
	'    ______                ______                     ' \
	'   / ____/(_)_______     / ____/___  _________ ___ ' \
	'  / /_   / // ___/ _ \  / /_  / __ \/ ___/ __ `__ \' \
	' / __/  / // /  /  __/ / __/ / /_/ / /  / / / / / /' \
	'/_/    /_//_/   \___/ /_/    \____/_/  /_/ /_/ /_/ ' \
	''
	@echo ""
	@echo "FireForm Development Commands"
	@echo "=============================="
	@echo "make init         - First-time setup: check deps, create .env.dev, pick model"
	@echo "make fireform     - Build images, start containers, pull Ollama model"
	@echo "make build        - Build Docker images"
	@echo "make up           - Start all containers (detached, bundled Ollama)"
	@echo "make up-native    - Start everything EXCEPT Ollama; use a host-native Ollama"
	@echo "make down         - Stop all containers"
	@echo "make logs         - Stream all container logs"
	@echo "make logs-app     - Stream app container logs"
	@echo "make logs-ollama  - Stream Ollama container logs"
	@echo "make shell        - Open shell in running app container"
	@echo "make pull-model   - Pull Ollama model from .env.dev ($(OLLAMA_MODEL))"
	@echo "make test         - Run test suite"
	@echo "make clean        - Stop containers (preserves volumes)"
	@echo "make super-clean  - [CAUTION] Stop containers, delete volumes, prune Docker"

init:
	@chmod +x scripts/check-deps.sh scripts/init-env.sh scripts/select-model.sh
	@sh scripts/check-deps.sh
	@sh scripts/init-env.sh
	@sh scripts/select-model.sh
	@printf "Build containers and pull model now? [y/N] "; \
	read answer; \
	case "$$answer" in \
		[yY]*) $(MAKE) fireform ;; \
		*) echo "Run 'make fireform' when ready." ;; \
	esac

fireform: build up
	@printf "Waiting for Ollama to be ready..."
	@until $(COMPOSE) exec -T ollama ollama list > /dev/null 2>&1; do \
		printf '.'; sleep 2; \
	done
	@echo " ready."
	@if $(COMPOSE) exec -T ollama ollama list 2>/dev/null | grep -q "^$(OLLAMA_MODEL)"; then \
		echo "  Model $(OLLAMA_MODEL) already pulled."; \
	else \
		echo "  Pulling $(OLLAMA_MODEL)..."; \
		$(COMPOSE) exec -T ollama ollama pull $(OLLAMA_MODEL); \
	fi
	@echo ""
	@echo "FireForm is ready!"
	@echo "   API:      http://localhost:8000"
	@echo "   API Docs: http://localhost:8000/docs"
	@echo ""
	@echo "Run 'make logs' to view live logs, 'make down' to stop."

build:
	@$(COMPOSE) build

up:
	@$(COMPOSE) up -d

# Run Ollama natively on the host (Metal/GPU on Mac); everything else in Docker.
up-native:
	@echo "Native Ollama mode — run these on the host first:"
	@echo "  1) OLLAMA_HOST=0.0.0.0:11434 ollama serve   (bind all interfaces)"
	@echo "  2) ollama pull $(OLLAMA_MODEL)"
	@echo "  3) set OLLAMA_HOST=http://host.docker.internal:11434 in $(ENV_DEV)"
	@$(COMPOSE_NATIVE) up -d

down:
	@$(COMPOSE) down --remove-orphans

logs:
	@$(COMPOSE) logs -f

logs-app:
	@$(COMPOSE) logs -f app

logs-ollama:
	@$(COMPOSE) logs -f ollama

shell:
	@$(COMPOSE) exec app /bin/sh

pull-model:
	@$(COMPOSE) exec -T ollama ollama pull $(OLLAMA_MODEL)

test:
	@$(COMPOSE) exec -T app python3 -m pytest tests/ -v

clean:
	@$(COMPOSE) down

super-clean:
	@echo "WARNING: this will delete all volumes (database, uploads, model weights)."
	@$(COMPOSE) down -v
	@docker system prune -f
