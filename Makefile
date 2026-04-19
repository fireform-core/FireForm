.PHONY: help build up down logs shell exec pull-model test clean fireform logs-app logs-ollama logs-frontend super-clean

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
	@echo "make logs-app     - View API container logs"
	@echo "make logs-frontend - View frontend container logs"
	@echo "make logs-ollama  - View Ollama container logs"
	@echo "make shell        - Open Python shell in app container"
	@echo "make exec         - Execute Python script in container"
	@echo "make pull-model   - Pull Mistral model into Ollama"
	@echo "make test         - Run tests"
	@echo "make clean        - Remove containers"
	@echo "make super-clean  - [CAUTION] Use carefully. Cleans up ALL stopped  containers, networks, build cache..."

# Fix #382 — pull-model is now part of the main setup flow
# Mistral is pulled automatically before you need it
fireform: build up pull-model
	@echo ""
	@echo "✅ FireForm is ready!"
	@echo "   API:      http://localhost:8000"
	@echo "   API Docs: http://localhost:8000/docs"
	@echo ""
	@echo "Run 'make logs' to view live logs, 'make down' to stop."

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

logs-frontend:
	docker compose logs -f frontend

shell:
	docker compose exec app /bin/bash

# Start the FastAPI server inside the running container
run:
	docker compose exec app uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

exec:
	docker compose exec app python3 src/main.py

pull-model:
	docker compose exec ollama ollama pull mistral

# Fix — correct test directory (was src/test/ which doesn't exist)
test:
	docker compose exec app python3 -m pytest tests/ -v

clean:
	docker compose down -v
super-clean:
	docker compose down -v
	docker system prune 
