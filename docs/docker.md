# Docker Documentation for FireForm

## Overview

FireForm uses Docker containers for easy deployment and development. The setup includes:

1. `fireform-app` - Main application container with API server and processing
2. `ollama/ollama:latest` - Local LLM server for AI processing

## Quick Start

### Prerequisites

- **Docker Engine** (20.10+) - [Installation Guide](https://docs.docker.com/engine/install/)
- **Docker Compose** (2.0+) - Included with Docker Desktop or install separately
- **Make** - For running development commands
- **Git** - For version control

### Initial Setup

Run the automated setup script:

```bash
chmod +x container-init.sh
./container-init.sh
```

> [!NOTE]
> This script pulls Ollama and Mistral model, so it may take several minutes to complete. Don't interrupt the process.

## Available Commands

Use the Makefile for easy container management:

```bash
make build        # Build Docker images
make up           # Start all containers
make down         # Stop all containers
make logs         # View logs from all containers
make shell        # Open bash shell in app container
make exec         # Run main.py in container
make pull-model   # Pull Mistral model into Ollama
make clean        # Remove all containers and volumes
make help         # Show all available commands
```

## Configuration Files

The Docker setup uses these files:

- `Dockerfile` - Main application container definition
- `docker-compose.yml` - Multi-container orchestration
- `Makefile` - Development commands
- `.dockerignore` - Files excluded from Docker build
- `container-init.sh` - Automated setup script

## Services

### FireForm App Container

- **Port**: 8000 (API server)
- **Features**: FastAPI server, PDF processing, database
- **Health Check**: Automatic health monitoring
- **Security**: Non-root user, resource limits

### Ollama Container

- **Port**: 11434 (LLM API)
- **Model**: Mistral (automatically pulled)
- **GPU Support**: Enabled if available
- **Persistence**: Model data persisted in volumes

## Development Workflow

1. **Start Development Environment**:

   ```bash
   make up
   ```

2. **View Application Logs**:

   ```bash
   make logs
   ```

3. **Access API Documentation**:
   Open `http://localhost:8000/docs`

4. **Run Commands in Container**:

   ```bash
   make shell
   ```

5. **Stop Environment**:
   ```bash
   make down
   ```

## Troubleshooting

### Common Issues

**Port 11434 Already in Use**:

```bash
sudo lsof -i :11434  # Check what's using the port
```

**Container Won't Start**:

```bash
make logs  # Check container logs
docker system prune  # Clean up Docker resources
```

**Model Not Loading**:

```bash
make pull-model  # Manually pull Mistral model
```

### Debugging

- **View All Logs**: `make logs`
- **Container Status**: `docker compose ps`
- **Resource Usage**: `docker stats`
- **Clean Reset**: `make clean && make build && make up`

## Security Features

The Docker setup includes:

- Non-root user execution
- Resource limits (CPU/memory)
- Network isolation
- Volume security
- Health checks
- Automatic restarts

## Production Deployment

For production use:

1. Update environment variables in `.env`
2. Configure proper SSL certificates
3. Set up reverse proxy (nginx/traefik)
4. Enable monitoring and logging
5. Configure backup strategies
