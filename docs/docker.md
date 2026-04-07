# Docker documentation for FireForm

## Setup
We will be using 3 containers:
1. `fireform-app` -> Runs the FastAPI server on `http://127.0.0.1:8000`.
2. `fireform-frontend` -> Serves the frontend on `http://127.0.0.1:5173`.
3. `ollama/ollama:latest` -> Runs Ollama for LLM calls.

### Initial configuration steps
For this I provided a script that can be run to automate the setup. 
This script builds both containers and starts them. 

You will have to make the script executable, this can be done in linux systems with:
```bash
chmod +x container-init.sh
```
The it can be run with:
```bash
./container-init.sh
```
- NOTE: This pulls ollama and mistral, so it's normal for it to take a long time to finish. Don't interrupt it.

## Dependencies
- **Docker Engine** (20.10+) - [Installation Guide](https://docs.docker.com/engine/install/)
- **Docker Compose** (2.0+) - Included with Docker Desktop or install separately
- **Make** - For running development commands
- **Git** - For version control

## Configuration files
The files involved in this are:
- Dockerfile
- Makefile
- docker-compose.yml
- .dockerignore (like gitignore but for the containers)
- container-init.sh

The makefile is set up so that you don't need to learn how to properly use docker, just use the __available commands:__
```
make build        # Build Docker images
make up           # Start all containers
make down         # Stop all containers
make logs         # View logs from all containers
make shell        # Open bash shell in app container
make exec         # Run main.py in container
make pull-model   # Pull Mistral model into Ollama
make clean        # Remove all containers and volumes
```
* You can see this list at any time by running `make help`.

## Running the full stack

```bash
make build
make up
```

Then open:
- Frontend: `http://127.0.0.1:5173`
- API docs: `http://127.0.0.1:8000/docs`

If this is your first run, pull the model once:

```bash
make pull-model
```

## Debugging
For debugging with LLMs it's really useful to attach the logs.
* You can obtain the logs using `make logs` or `docker compose logs`.
* A common problem is when you already have something running in port 11434. As ollama runs in that port, we need it free. You can check what's running on that port with `sudo lsof -i  :11434`.
