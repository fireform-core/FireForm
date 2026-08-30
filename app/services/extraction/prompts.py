"""Chunk prompts.

Every chunk prompt is a static prefix plus a dynamic suffix. The prefix (the
instructions and the chunk's field skeleton) never changes between incidents,
so Ollama reuses its KV cache for it; only the tail, which carries the
deployment context and the narrative, is new each time. Interpolating the
narrative anywhere but the end would throw that away.

The field skeleton is rendered from the generated Pydantic model rather than
hand-written, so it cannot drift from the contract. Enum members are spelled
out because small models invent enum values otherwise.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from enum import Enum
from functools import lru_cache
from typing import Any, get_args, get_origin
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, NaiveDatetime, RootModel

from app.services.extraction.registry import ChunkSpec

# How deep the skeleton goes before it stops describing nested shape. Three
# levels covers every chunk in the contract without bloating the prompt.
MAX_DEPTH = 3

# Longest enum spelled out in full. Past this the prompt lists the first few
# and tells the model to use exactly one of the contract's values.
MAX_ENUM_MEMBERS = 25

INSTRUCTIONS = """You extract fire and emergency incident data from a responder's narrative.

Rules:
- Return one JSON object and nothing else. No prose, no markdown, no code fence.
- Use only facts the narrative states or clearly implies. Never invent a value.
- Leave out any field the narrative does not support. An absent field is correct; a guess is not.
- Use exactly the enum values listed. If none fits, leave the field out.
- Date-times are RFC 3339 with an offset, for example 2026-04-18T21:14:00-07:00.
- Physical quantities are SI: metres, square metres, hectares, litres, kilometres, Celsius.
"""


def _enum_hint(enum_cls: type[Enum]) -> str:
    members = [str(member.value) for member in enum_cls]
    if len(members) > MAX_ENUM_MEMBERS:
        shown = " | ".join(members[:MAX_ENUM_MEMBERS])
        return f"<one of: {shown} | ... (use an exact contract value)>"
    return f"<one of: {' | '.join(members)}>"


# Pydantic's date-time markers are plain classes at runtime, not datetime
# subclasses, so they need naming before the subclass checks below.
_ALIAS_HINTS: dict[Any, str] = {
    AwareDatetime: "<date-time, RFC 3339 with offset>",
    NaiveDatetime: "<date-time, RFC 3339>",
}

_SCALAR_HINTS: dict[type, str] = {
    str: "<string>",
    bool: "<true or false>",
    int: "<integer>",
    float: "<number>",
    datetime: "<date-time, RFC 3339>",
    date: "<date, YYYY-MM-DD>",
    time: "<time, HH:MM:SS>",
    UUID: "<uuid>",
}


def _skeleton(annotation: Any, depth: int) -> Any:
    """Render one field's expected shape as a placeholder value."""
    hint = _ALIAS_HINTS.get(annotation)
    if hint is not None:
        return hint

    origin = get_origin(annotation)

    if origin is list:
        args = [a for a in get_args(annotation) if a is not type(None)]
        item = _skeleton(args[0], depth) if args else "<value>"
        return [item]

    if origin is not None:
        # Optional / Union / Annotated: describe the first real member.
        args = [a for a in get_args(annotation) if a is not type(None)]
        return _skeleton(args[0], depth) if args else "<value>"

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return _enum_hint(annotation)

    if isinstance(annotation, type) and issubclass(annotation, RootModel):
        # A root model is a wrapper around one value; describe the value.
        return _skeleton(annotation.model_fields["root"].annotation, depth)

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if depth >= MAX_DEPTH:
            return "<object>"
        return model_skeleton(annotation, depth + 1)

    if isinstance(annotation, type):
        for scalar, hint in _SCALAR_HINTS.items():
            if issubclass(annotation, scalar):
                return hint

    return "<value>"


def model_skeleton(model: type[BaseModel], depth: int = 0) -> dict[str, Any]:
    """A JSON-shaped description of every field on a generated contract model."""
    skeleton: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        skeleton[name] = _skeleton(info.annotation, depth)
    return skeleton


@lru_cache(maxsize=None)
def static_prefix(chunk_name: str, model: type[BaseModel], is_list: bool, description: str) -> str:
    """The cacheable head of a chunk prompt. Identical for every incident."""
    shape = model_skeleton(model)
    body = {chunk_name: [shape] if is_list else shape}
    lines = [INSTRUCTIONS]
    if description:
        lines.append(f"Section: {chunk_name}. {description}")
    else:
        lines.append(f"Section: {chunk_name}.")
    lines.append(
        f'Return a JSON object with the single key "{chunk_name}", shaped like this. '
        "The angle-bracket text describes the expected value, it is not a value:"
    )
    lines.append(json.dumps(body, indent=2))
    return "\n\n".join(lines)


def build_prompt(
    spec: ChunkSpec,
    text: str,
    context_lines: list[str],
    retry_note: str | None = None,
) -> str:
    """The full prompt for one chunk: cached prefix, then this incident's tail."""
    prefix = static_prefix(spec.name, spec.model, spec.is_list, spec.description)
    tail = ["Context for resolving anything the narrative leaves implicit:"]
    tail.extend(f"- {line}" for line in context_lines)
    if retry_note:
        tail.append(
            "Your previous answer was rejected. Fix it and return the corrected "
            f"JSON object only. Reason: {retry_note}"
        )
    tail.append(f"NARRATIVE:\n{text}")
    return prefix + "\n\n" + "\n\n".join(tail)
