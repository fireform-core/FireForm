"""LLM endpoints: GET /api/v1/system/llm/models, POST /api/v1/system/llm/test, POST /api/v1/system/llm/pull.

Contract: contracts/path/system.yaml + contracts/schemas/system.yaml
"""

from fastapi import APIRouter
from fastapi import Depends
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlmodel import Session

from app.api.deps import get_db
from app.api.schemas.enums import LLMProvider
from app.api.schemas.system import (
    DownloadableModel,
    LLMModelChoice,
    LLMModelDeleteRequest,
    LLMModelDeleteResult,
    LLMModels,
    LLMProviderModels,
    LLMPullRequest,
    LLMTestRequest,
    LLMTestResult,
    ModelInfo,
)
from app.services import llm
from app.services.llm.errors import (
    LLMModelInUseError,
    LLMModelNotInstalledError,
    LLMNotAvailableError,
)
from app.services.llm.ollama import OllamaLLM

router = APIRouter(prefix="/system/llm", tags=["system"])


# Fields without a value are left out: hosted providers only give a model name,
# Ollama adds size, quantization, whether the model is loaded, and downloadable models.
@router.get(
    "/models",
    response_model=LLMModels,
    response_model_exclude_none=True,
    summary="List the LLM providers and models that can fill forms",
)
def list_llm_models(refresh: bool = False, db: Session = Depends(get_db)):
    registry = llm.effective_registry(db)
    providers: list[LLMProviderModels] = []
    for c in registry.catalog(refresh):
        downloadable = (
            [DownloadableModel.model_validate(d) for d in c.downloadable]
            if c.downloadable
            else None
        )
        providers.append(
            LLMProviderModels(
                provider=c.provider,
                available=c.available,
                default_model=c.default_model,
                detail=c.detail,
                error_code=c.error_code,
                models=[ModelInfo.model_validate(m) for m in c.models],
                downloadable=downloadable,
            )
        )
    return LLMModels(
        default=LLMModelChoice.model_validate(registry.default),
        providers=providers,
    )


@router.post(
    "/test",
    response_model=LLMTestResult,
    response_model_exclude_none=True,
    summary="Check that a model actually answers",
)
def test_llm_model(body: LLMTestRequest | None = None, db: Session = Depends(get_db)):
    body = body or LLMTestRequest()
    check = llm.ModelValidator(llm.effective_registry(db)).probe(body.provider, body.model)
    return LLMTestResult.model_validate(check)


@router.post(
    "/pull",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"application/x-ndjson": {}}},
        422: {"description": "Invalid pull request or model not installable"},
        503: {"description": "Ollama service unavailable"},
    },
    summary="Pull an AI model from Ollama",
)
def pull_llm_model(req: LLMPullRequest, db: Session = Depends(get_db)):
    registry = llm.effective_registry(db)
    provider_val = req.provider or "ollama"
    registry.validate_pull(provider_val, req.model)

    client = registry.client(LLMProvider.ollama)
    if not isinstance(client, OllamaLLM):
        raise LLMNotAvailableError("Model pulling is only supported for Ollama.")

    stream = client.pull_model(
        req.model,
        on_success=lambda: registry.provider_catalog(LLMProvider.ollama, refresh=True),
    )
    return StreamingResponse(
        stream,
        media_type="application/x-ndjson",
        background=BackgroundTask(stream.close),
    )


@router.delete(
    "/models",
    response_model=LLMModelDeleteResult,
    responses={
        404: {"description": "Ollama does not have the model installed"},
        409: {"description": "The model is a default or currently being pulled"},
        422: {"description": "Invalid request or model is not allowed"},
        502: {"description": "Ollama returned an unexpected response"},
        503: {"description": "Ollama service unavailable"},
    },
    summary="Delete an installed Ollama model",
)
def delete_llm_model(req: LLMModelDeleteRequest, db: Session = Depends(get_db)):
    registry = llm.effective_registry(db)
    registry.validate_pull(req.provider, req.model)

    client = registry.client(LLMProvider.ollama)
    if not isinstance(client, OllamaLLM):
        raise LLMNotAvailableError("Model deletion is only supported for Ollama.")

    catalog = registry.provider_catalog(LLMProvider.ollama, refresh=True)
    if catalog.error:
        raise type(catalog.error)(catalog.error.message)
    if not any(model.name == req.model and model.installed is True for model in catalog.models):
        raise LLMModelNotInstalledError(f"Ollama does not have model {req.model} installed.")

    ollama_default = registry.settings.providers[LLMProvider.ollama].default_model
    if (
        registry.default.provider is LLMProvider.ollama
        and registry.default.model == req.model
    ):
        raise LLMModelInUseError(f"Cannot delete {req.model}: it is the global default model.")
    if ollama_default == req.model:
        raise LLMModelInUseError(f"Cannot delete {req.model}: it is the Ollama provider default model.")
    if client.is_model_pulling(req.model):
        raise LLMModelInUseError(f"Cannot delete {req.model}: a download is currently active.")

    client.delete_model(req.model)
    registry.provider_catalog(LLMProvider.ollama, refresh=True)
    return LLMModelDeleteResult(model=req.model, deleted=True)
