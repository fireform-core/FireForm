# Contributing to FireForm

First of all, thank you for considering contributing to FireForm! It's people like you that make FireForm a great tool for first responders.

FireForm is a Digital Public Good (DPG) designed to reduce administrative overhead for firefighters and other emergency services. By contributing, you are helping us build a more efficient future for emergency response.

>**NOTE: Before you contribute!**
>Please note that this project is still under early development. Because of this you may find many bugs caused either by cases yet unaddressed that we are aware of. Reports on these bugs will be dismissed to remove clutter, so please don't feel discouraged if your issue is dismissed quickly, it just means we were already aware of the bug.

## 🌈 Code of Conduct

This project and everyone participating in it is governed by the [FireForm Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to juanalvarez_san@protonmail.com.

## 🚀 How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the [issues list](https://github.com/juanalvv/FireForm/issues) to see if the problem has already been reported.

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

## 🛠️ Local Development Setup

FireForm uses Docker and Docker Compose for the backend to ensure a consistent environment.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- `make` (optional, but recommended)
- [Node.js](https://nodejs.org/) 20+ (only needed for the desktop app)

### Desktop App Development

The frontend is a vanilla HTML/CSS/JS app wrapped in Electron. To run it locally:

```bash
cd frontend
npm install    # one-time setup
npm start      # launches the Electron desktop window
```

The backend (API + Ollama) must be running separately via Docker — see `make fireform`.
