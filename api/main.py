from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
from api.routes import templates, forms
from api.errors.handlers import register_exception_handlers
from api.errors.base import LLMUnavailableError

app = FastAPI()

register_exception_handlers(app)

app.include_router(templates.router)
app.include_router(forms.router)


@app.get("/health/llm", tags=["health"])
async def llm_healthcheck():
    """
    Lightweight health check for the LLM backend (Ollama).

    Uses the cheap /api/tags endpoint so we don't have to load a model.
    """
    from src.llm import LLM

    llm = LLM(transcript_text="", target_fields={"healthcheck": ""})
    generate_url = llm._get_ollama_url()
    ollama_host = generate_url.rsplit("/api/generate", 1)[0]
    tags_url = f"{ollama_host}/api/tags"

    try:
        response = requests.get(tags_url, timeout=5)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise LLMUnavailableError(
            "LLM backend unreachable. Ensure Ollama is running (`ollama serve`) "
            "and that OLLAMA_HOST is set correctly."
        )
    except requests.exceptions.HTTPError as e:
        raise LLMUnavailableError(f"LLM backend returned an HTTP error: {e}")
    except requests.exceptions.RequestException as e:
        raise LLMUnavailableError(f"LLM healthcheck failed: {e}")

    return JSONResponse({"status": "ok"})