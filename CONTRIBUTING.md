# Contributing to FireForm

First of all, thank you for considering contributing to FireForm! It's people like you that make FireForm a great tool for first responders.

FireForm is a Digital Public Good (DPG) designed to reduce administrative overhead for firefighters and other emergency services. By contributing, you are helping us build a more efficient future for emergency response.

> **NOTE: Before you contribute!**
> Please note that this project is still under early development. Because of this you may find many bugs caused either by cases yet unaddressed that we are aware of. Reports on these bugs will be dismissed to remove clutter, so please don't feel discouraged if your issue is dismissed quickly, it just means we were already aware of the bug.

## 🌈 Code of Conduct

This project and everyone participating in it is governed by the [FireForm Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to juanalvarez_san@protonmail.com.

## 🚀 How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the [issues list](https://github.com/fireform-core/FireForm/issues) to see if the problem has already been reported.

When you are creating a bug report, please include as many details as possible:
* **Use a clear and descriptive title** for the issue to identify the problem.
* **Use the bug report template** to ensure you include all the necessary information.
* **Describe the exact steps which reproduce the problem** in as many details as possible.
* **Explain which behavior you expected to see instead and why.**
* **Include screenshots** if applicable.

### Suggesting Enhancements

If you have a great idea for FireForm, we'd love to hear it! Please open an issue and include:
* **A clear and descriptive title.**
* **A step-by-step description of the suggested enhancement** in as many details as possible.
* **Explain why this enhancement would be useful** to the users.

### Pull Requests

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. Ensure the test suite passes.
4. Make sure your code lints.
5. Issue that pull request!

## 🛠️ Development Setup

For detailed, platform-specific setup instructions (Windows, macOS, Linux), see the [Developer Setup Guide](docs/SETUP.md).

### Prerequisites

- [Python 3.11+](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/)
- [Ollama](https://ollama.com/download) (for running the LLM locally)
- `make` (optional, but recommended — included with most Linux/macOS systems)

### Quick Start (Docker)

```bash
# 1. Clone your fork
git clone https://github.com/<your-username>/FireForm.git
cd FireForm

# 2. Build and start all containers
make build
make up

# 3. Pull the Mistral model into Ollama
make pull-model

# 4. Open a shell in the app container
make shell
```

### Quick Start (Local — without Docker)

```bash
# 1. Clone and set up virtual environment
git clone https://github.com/<your-username>/FireForm.git
cd FireForm
python -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate
# Activate (Windows)
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize the database
python -m api.db.init_db

# 4. Start the API server
uvicorn api.main:app --reload

# 5. In a separate terminal, start Ollama
ollama serve
ollama pull mistral
```

### Verifying Your Setup

Once the API is running, verify it:

```bash
# Should return {"detail":"Not Found"} or a health response
curl http://localhost:8000/docs
```

Then open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser to see the Swagger UI.

## 🧪 Running Tests

```bash
# Local
python -m pytest tests/ -v

# Docker
make test
```

> **Note:** The `make test` command currently points to `src/test/`. The main test directory is `tests/` at the project root. When running locally, always use `python -m pytest tests/ -v`.

## 🌿 Branch Naming Convention

Please follow these branch naming conventions:

| Type | Format | Example |
|------|--------|---------|
| Feature | `feat/<short-description>` | `feat/batch-extraction` |
| Bug fix | `fix/<short-description>` | `fix/json-decode-error` |
| Refactor | `refactor/<short-description>` | `refactor/llm-client` |
| Documentation | `docs/<short-description>` | `docs/setup-guide` |
| Tests | `test/<short-description>` | `test/llm-unit-tests` |

## 📝 Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <short description>

Examples:
feat(api): add GET /forms/download endpoint
fix(filler): correct multi-page field index reset
docs: add developer setup guide
test(llm): add batch extraction unit tests
```

## 📂 Project Structure

```
FireForm/
├── api/                    # FastAPI backend
│   ├── db/                 # Database models, repositories, init
│   ├── routes/             # API route handlers (forms, templates)
│   ├── schemas/            # Pydantic request/response models
│   ├── errors/             # Custom error classes and handlers
│   └── main.py             # FastAPI app entry point
├── src/                    # Core pipeline logic
│   ├── controller.py       # Orchestrates extraction → filling
│   ├── file_manipulator.py # Manages LLM + PDF coordination
│   ├── filler.py           # PDF form filling with pdfrw
│   ├── llm.py              # Ollama/Mistral LLM client
│   ├── main.py             # Standalone CLI entry point
│   ├── inputs/             # Sample input files (PDFs, transcripts)
│   └── outputs/            # Generated filled PDFs
├── tests/                  # Test suite (pytest)
├── docs/                   # Documentation
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Multi-container orchestration
├── Makefile                # Development convenience commands
└── requirements.txt        # Python dependencies
```

## 🔗 Useful Links

- [Project Board](https://github.com/users/juanalvv/projects/1) — Task tracking
- [Swagger API Docs](http://localhost:8000/docs) — Interactive API explorer (when server is running)
- [Docker Guide](docs/docker.md) — Docker-specific documentation
- [Database Guide](docs/db.md) — Database setup and management
- [Developer Setup Guide](docs/SETUP.md) — Comprehensive setup instructions
