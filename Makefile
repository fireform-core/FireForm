.PHONY: help build up down logs shell exec pull-model test test-local test-cov clean fireform

help:
	@printf '%s\n' \
	'    ______                ______                     ' \
	'   / ____/(_)_______     / ____/___  _________ ___ ' \
	'  / /_   / // ___/ _ \  / /_  / __ \/ ___/ __ `__ \' \
	' / __/  / // /  /  __/ / __/ / /_/ / /  / / / / / /' \
	'/_/    /_//_/   \___/ /_/    \____/_/  /_/ /_/ /_/ ' \
	''
	@echo ""
	@echo "Fireform Development Commands"
	@echo "=============================="
	@echo "make fireform     - Build and start containers, then open a shell"
	@echo "make build        - Build Docker images"
	@echo "make up           - Start all containers"
	@echo "make down         - Stop all containers"
	@echo "make logs         - View container logs"
	@echo "make shell        - Open Python shell in app container"
	@echo "make exec         - Execute Python script in container"
	@echo "make pull-model   - Pull Mistral model into Ollama"
	@echo "make test         - Run tests inside Docker container"
	@echo "make test-local   - Run tests locally without Docker"
	@echo "make test-cov     - Run tests locally with coverage report"
	@echo "make clean        - Remove containers"
	@echo "make super-clean  - [CAUTION] Use carefully. Cleans up ALL stopped  containers, networks, build cache..."

fireform: build up
	@echo "Launching interactive shell in the app container..."
	docker compose exec app /bin/bash

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

logs-app:
	docker compose logs -f app

logs-ollama:
	docker compose logs -f ollama

shell:
	docker compose exec app /bin/bash

exec:
	docker compose exec app python3 src/main.py

pull-model:
	docker compose exec ollama ollama pull mistral

test:
	docker compose exec app python3 -m pytest tests/ -v

test-local:
	python3 -m pytest tests/ -v

test-cov:
	python3 -m pytest tests/ --cov=api --cov=src --cov-report=term-missing

clean:
	docker compose down -v
super-clean:
	docker compose down -v
	docker system prune 
