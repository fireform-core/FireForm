.PHONY: help init fireform build up down logs logs-app logs-ollama shell pull-model test benchmark clean super-clean status ready-banner sync docs

COMPOSE     = docker compose -f docker/dev/compose.yml --env-file docker/.env.dev
ENV_DEV     = docker/.env.dev

# Docker mode owns the Ollama container and model. External mode only points
# FireForm at an Ollama server managed by the user.
OLLAMA_MODEL = $(or $(shell grep -E '^OLLAMA_MODEL=' $(ENV_DEV) 2>/dev/null | cut -d= -f2 | tr -d '[:space:]'),qwen2.5:1.5b)
OLLAMA_MODE  = $(or $(shell grep -E '^OLLAMA_MODE=' $(ENV_DEV) 2>/dev/null | cut -d= -f2 | tr -d '[:space:]'),docker)
OLLAMA_HOST  = $(or $(shell grep -E '^OLLAMA_HOST=' $(ENV_DEV) 2>/dev/null | cut -d= -f2 | tr -d '[:space:]'),http://ollama:11434)
COMPOSE_LOCAL_LLM = $(COMPOSE) --profile local-llm
BENCHMARK_CASES ?= ics201_1
BENCHMARK_CONCURRENCY ?= 1
BENCHMARK_TIMEOUT_SECONDS ?= 7200

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
	@echo "make fireform     - Build and start FireForm (Ollama follows OLLAMA_MODE)"
	@echo "make build        - Build Docker images"
	@echo "make up           - Start all containers (detached)"
	@echo "make down         - Stop all containers"
	@echo "make sync         - Fast-install new requirements.txt deps into running app (no rebuild)"
	@echo "make status       - Show compact container health summary"
	@echo "make logs         - Stream all container logs"
	@echo "make logs-app     - Stream app container logs"
	@echo "make logs-ollama  - Stream Ollama container logs"
	@echo "make logs-worker  - Stream Celery worker logs"
	@echo "make shell        - Open shell in running app container"
	@echo "make pull-model   - Pull Ollama model from .env.dev ($(OLLAMA_MODEL))"
	@echo "make test         - Run test suite"
	@echo "make benchmark    - Run live extraction benchmark (default: ics201_1)"
	@echo "make docs         - Serve interactive API docs from the OpenAPI contract"
	@echo "make migrate      - Run pending Alembic migrations"
	@echo "make migration    - Generate new migration (msg='description')"
	@echo "make generate-contract-models - Regenerate Pydantic models from the incident contract"
	@echo "make clean        - Stop containers (preserves volumes)"
	@echo "make super-clean  - [CAUTION] Stop containers, delete volumes, prune Docker"

init:
	@chmod +x scripts/check-deps.sh scripts/init-env.sh scripts/select-model.sh
	@sh scripts/check-deps.sh
	@sh scripts/init-env.sh
	@sh scripts/select-model.sh
	@printf "Build and start FireForm now? [y/N] "; \
	read answer; \
	case "$$answer" in \
		[yY]*) $(MAKE) fireform ;; \
		*) echo "Run 'make fireform' when ready." ;; \
	esac

fireform:
	@set -e; \
	if [ "$(OLLAMA_MODE)" = "docker" ]; then \
		$(COMPOSE_LOCAL_LLM) up -d --build; \
		if $(COMPOSE_LOCAL_LLM) exec -T ollama ollama list 2>/dev/null | grep -q "^$(OLLAMA_MODEL)"; then \
			echo "  Model $(OLLAMA_MODEL) already pulled."; \
		else \
			echo "  Pulling $(OLLAMA_MODEL)..."; \
			$(COMPOSE_LOCAL_LLM) exec -T ollama ollama pull $(OLLAMA_MODEL); \
		fi; \
	else \
		$(COMPOSE_LOCAL_LLM) stop ollama >/dev/null 2>&1 || true; \
		$(COMPOSE) up -d --build; \
		echo "  Using external Ollama at $(OLLAMA_HOST); skipping model pull."; \
	fi
	@$(MAKE) --no-print-directory ready-banner

build:
	@$(COMPOSE) build

up:
	@if [ "$(OLLAMA_MODE)" = "docker" ]; then \
		$(COMPOSE_LOCAL_LLM) up -d; \
	else \
		$(COMPOSE_LOCAL_LLM) stop ollama >/dev/null 2>&1 || true; \
		$(COMPOSE) up -d; \
		echo "  Using external Ollama at $(OLLAMA_HOST)."; \
	fi
	@$(MAKE) --no-print-directory ready-banner

# Fast path for "I added a package": install the delta into the running container
# (no image rebuild, no 1.6GB layer re-export). uv installs only what's missing in
sync:
	@$(COMPOSE) exec -T app sh -c "UV_TORCH_BACKEND=cpu uv pip install --system -r requirements.txt"

status:
	@$(COMPOSE) ps --format 'table {{.Service}}\t{{.Status}}'

ready-banner:
	@echo ""
	@echo "FireForm is ready!"
	@echo "   API:      http://localhost:8000"
	@echo "   API Docs: http://localhost:8000/docs"
	@echo ""
	@echo "Run 'make logs' to view live logs, 'make down' to stop."

down:
	@$(COMPOSE_LOCAL_LLM) down --remove-orphans

logs:
	@$(COMPOSE) logs -f

logs-app:
	@$(COMPOSE) logs -f app

logs-ollama:
	@$(COMPOSE) logs -f ollama

logs-worker:
	@$(COMPOSE) logs -f celery-worker

shell:
	@$(COMPOSE) exec app /bin/sh

pull-model:
	@if [ "$(OLLAMA_MODE)" = "docker" ]; then \
		$(COMPOSE_LOCAL_LLM) up -d ollama; \
		$(COMPOSE_LOCAL_LLM) exec -T ollama ollama pull $(OLLAMA_MODEL); \
	else \
		echo "OLLAMA_MODE=external; manage model $(OLLAMA_MODEL) on $(OLLAMA_HOST)."; \
	fi

test:
	@$(COMPOSE) exec -T app python3 -m pytest tests/ benchmark/ -m "not live_benchmark" -v

benchmark:
	@BENCHMARK_CASES="$(BENCHMARK_CASES)" RUN_LIVE_BENCHMARK=1 python3 -m pytest benchmark/test_benchmark.py -v

docs:
	@echo "Serving Swagger UI from contracts/openapi.yaml at http://localhost:8088"
	@npx --yes swagger-ui-watcher contracts/openapi.yaml --port 8088

migrate:
	@$(COMPOSE) exec -T app alembic upgrade head

migration:
	@test -n "$(rev)" || { echo "rev is required, e.g. make migration rev=003 msg=\"...\""; exit 1; }
	@$(COMPOSE) exec -T app alembic revision --autogenerate --rev-id "$(rev)" -m "$(msg)"

generate-contract-models:
	@$(COMPOSE) exec -T app sh -c "uv pip install --system -r requirements-dev.txt && python3 scripts/generate_contract_models.py"

clean:
	@$(COMPOSE) down

super-clean:
	@echo "WARNING: this will delete all volumes (database, uploads, model weights)."
	@$(COMPOSE) down -v
	@docker system prune -f
