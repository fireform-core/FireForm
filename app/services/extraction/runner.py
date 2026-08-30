"""Running the selected chunks.

Each chunk is one focused prompt, validated against its generated model. A
chunk that comes back malformed gets one retry with the reason named. If it
misses again, the salvage pass keeps whatever fields do validate and throws
away only the offending ones, because one invented enum in a sub-field nobody
mentioned should not cost a whole section. Nothing is ever guessed in the other
direction: fields only come out. Chunks run in waves by tier so the fields a
form needs land first, and inside a wave they run in parallel up to the
provider's concurrency limit.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import groupby
from typing import Any, Callable

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.core.config import EXTRACTION_CHUNK_RETRIES, EXTRACTION_MAX_PARALLEL
from app.core.logging import get_logger
from app.services import llm
from app.services.extraction.prompts import build_prompt
from app.services.extraction.registry import ChunkSpec

logger = get_logger(__name__)


@dataclass
class ChunkResult:
    """What one chunk produced: a validated value, or the reason it has none."""

    name: str
    value: Any = None
    error: str | None = None
    attempts: int = 0
    # Paths thrown away by the salvage pass, so the review screen can show them
    # as gaps rather than pretending the whole section was extracted.
    dropped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def has_value(self) -> bool:
        return self.value not in (None, {}, [])


@lru_cache(maxsize=None)
def _list_adapter(model: type[BaseModel]) -> TypeAdapter:
    """Validator for a list-valued chunk, built once per chunk model."""
    return TypeAdapter(list[model])


def _validate(spec: ChunkSpec, payload: dict[str, Any]) -> Any:
    """Validate the model's answer against the chunk's contract model.

    The prompt asks for {"chunk_name": {...}}, but models sometimes return the
    inner object on its own, so both shapes are accepted. Returns plain JSON
    data with unset fields dropped, ready for the contract document.
    """
    raw = payload.get(spec.name, payload)

    if spec.is_list:
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            raise ValueError(f"expected a list for {spec.name}, got {type(raw).__name__}")
        # Validated as a whole list, not item by item, so an error's location
        # carries the index the salvage pass needs to find the offending entry.
        validated = _list_adapter(spec.model).validate_python(raw)
        items = [item.model_dump(mode="json", exclude_none=True) for item in validated]
        return [item for item in items if item]

    if not isinstance(raw, dict):
        raise ValueError(f"expected an object for {spec.name}, got {type(raw).__name__}")
    return spec.model.model_validate(raw).model_dump(mode="json", exclude_none=True)


def _drop_path(payload: Any, path: tuple) -> str | None:
    """Delete one validation-error path from the raw answer.

    Returns the path it removed, or None when the path does not resolve (a
    union tag in the location, an index that moved). Nothing is guessed: only
    an exact hit is deleted.
    """
    node = payload
    for step in path[:-1]:
        if isinstance(node, dict) and step in node:
            node = node[step]
        elif isinstance(node, list) and isinstance(step, int) and step < len(node):
            node = node[step]
        else:
            return None

    last = path[-1]
    if isinstance(node, dict) and last in node:
        del node[last]
    elif isinstance(node, list) and isinstance(last, int) and last < len(node):
        del node[last]
    else:
        return None
    return ".".join(str(step) for step in path)


def _salvage(spec: ChunkSpec, raw: Any, exc: ValidationError) -> tuple[Any, list[str]]:
    """Keep the fields that validate by dropping the ones that do not.

    A small model will invent an enum value in some sub-field nobody mentioned,
    and without this one bad field costs the whole section. Dropping the exact
    offending paths and validating again keeps the good data. Nothing is
    invented here; fields only ever come out.
    """
    dropped: list[str] = []
    error = exc

    def deepest_first(path: tuple) -> tuple:
        """Sort key: remove the longest paths and the highest list indices
        first, so deleting one entry cannot shift another out from under us."""
        return tuple((1, step) if isinstance(step, int) else (0, str(step)) for step in path)

    # Each pass can uncover errors the previous one masked, so try a few times.
    for _ in range(3):
        removed_any = False
        paths = sorted({tuple(err["loc"]) for err in error.errors()}, key=deepest_first, reverse=True)
        for path in paths:
            removed = _drop_path(raw, path)
            if removed:
                dropped.append(removed)
                removed_any = True
        if not removed_any:
            break
        try:
            return _validate(spec, {spec.name: raw}), dropped
        except ValidationError as next_error:
            error = next_error
        except ValueError:
            break

    raise error


def _failure_reason(exc: Exception) -> str:
    """A short, model-readable description of why an answer was rejected."""
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors()[:5]:
            path = ".".join(str(loc) for loc in err["loc"]) or "value"
            parts.append(f"{path}: {err['msg']}")
        return "; ".join(parts)
    return str(exc)


def extract_chunk(
    spec: ChunkSpec,
    text: str,
    context_lines: list[str],
    model: str | None = None,
    gate: llm.RateLimitGate | None = None,
) -> ChunkResult:
    """Extract one chunk: retry a rejected answer once, then salvage what validates."""
    result = ChunkResult(name=spec.name)
    retry_note: str | None = None
    attempts = 1 + EXTRACTION_CHUNK_RETRIES

    for attempt in range(attempts):
        result.attempts = attempt + 1
        last_try = attempt == attempts - 1
        prompt = build_prompt(spec, text, context_lines, retry_note)
        try:
            payload = llm.generate_json(prompt, model=model, gate=gate)
            result.value = _validate(spec, payload)
            result.error = None
            return result
        except (llm.LLMUnavailableError, llm.LLMRateLimitError, llm.LLMAuthError):
            # Nothing chunk-specific about these. Every other chunk would hit
            # the same wall, so the run gives up rather than working through it.
            raise
        except llm.LLMTimeoutError as exc:
            result.error = str(exc)
            logger.warning("chunk %s timed out, not retrying: %s", spec.name, exc)
            break
        except ValidationError as exc:
            retry_note = _failure_reason(exc)
            result.error = retry_note
            logger.warning(
                "chunk %s attempt %d rejected: %s", spec.name, result.attempts, retry_note
            )
            if not last_try:
                continue
            try:
                raw = payload.get(spec.name, payload)
                result.value, result.dropped = _salvage(spec, raw, exc)
                result.error = None
                logger.info(
                    "chunk %s salvaged, dropped %d field(s): %s",
                    spec.name,
                    len(result.dropped),
                    ", ".join(result.dropped),
                )
                return result
            except (ValidationError, ValueError):
                logger.warning("chunk %s could not be salvaged", spec.name)
        except (llm.LLMResponseError, ValueError) as exc:
            retry_note = _failure_reason(exc)
            result.error = retry_note
            logger.warning(
                "chunk %s attempt %d rejected: %s", spec.name, result.attempts, retry_note
            )

    logger.error(
        "chunk %s failed after %d attempt(s), left for manual entry: %s",
        spec.name,
        result.attempts,
        result.error,
    )
    result.value = None
    return result


def run_chunks(
    specs: list[ChunkSpec],
    text: str,
    context_lines: list[str],
    model: str | None = None,
    on_wave: Callable[[list[ChunkResult]], None] | None = None,
) -> list[ChunkResult]:
    """Run every selected chunk, one parallel wave per tier.

    `on_wave` is called with the results of each wave as it lands, which is how
    the worker publishes partial results while the long tail is still running.
    """
    results: list[ChunkResult] = []
    workers = max(1, EXTRACTION_MAX_PARALLEL)
    # Shared by every chunk in this run. The first one to exhaust its rate limit
    # retries trips it, and the rest fail immediately instead of each waiting.
    gate = llm.RateLimitGate()

    for tier, group in groupby(specs, key=lambda s: s.tier):
        wave = list(group)
        logger.info("extracting %s wave: %s", tier.value, ", ".join(s.name for s in wave))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            wave_results = list(
                pool.map(lambda spec: extract_chunk(spec, text, context_lines, model, gate), wave)
            )
        results.extend(wave_results)
        if on_wave is not None:
            on_wave(wave_results)

    return results
