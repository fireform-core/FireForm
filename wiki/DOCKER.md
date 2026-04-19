# Docker Documentation

FireForm uses Docker to ensure a consistent environment across different machines.

## Container Stack

We use three main containers:
1.  **`fireform-app`**: Runs the FastAPI server on `http://localhost:8000`.
2.  **`fireform-frontend`**: Serves the frontend on `http://localhost:5173`.
3.  **`fireform-ollama`**: Runs Ollama for LLM calls.

## Makefile Commands

The `Makefile` simplifies common Docker tasks. You can run these commands from the project root:

| Command | Description |
| :--- | :--- |
| `make build` | Build Docker images |
| `make up` | Start all containers in the background |
| `make down` | Stop all containers |
| `make logs` | View logs from all containers |
| `make shell` | Open a bash shell in the app container |
| `make pull-model` | Pull the Mistral model into Ollama |
| `make clean` | Remove all containers and volumes |
| `make help` | Show all available commands |

## Troubleshooting

- **Logs:** Use `make logs` to see what's happening inside the containers.
- **Port Conflicts:** If port 11434 (Ollama) or 8000 (App) is already in use, you may need to stop the conflicting process or change the mapping in `docker-compose.yml`.
- **Model not found:** If LLM calls fail, ensure you've run `make pull-model`.
