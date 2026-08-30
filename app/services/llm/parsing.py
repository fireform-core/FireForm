"""Reading a JSON object out of whatever the model actually said.

Even with JSON mode on, a small model will wrap its answer in a code fence or
put a sentence in front of it, and no provider offers JSON mode on every model
we support. So the parser tolerates both rather than throwing away a good answer
over formatting, and rebuilds an answer that was cut off at the token ceiling
instead of losing the whole thing.

Lifted from the extraction chunk client, which is where it earned its keep.
Every provider needs it now, so it lives here.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.services.llm.errors import LLMResponseError

logger = get_logger(__name__)


def close_truncated(text: str) -> str | None:
    """Rebuild a JSON object that was cut off mid answer, or return None.

    An answer that hits the token ceiling ends in the middle of a value and
    parses as nothing, losing a section that was mostly fine. This trims back to
    the last point the text was known to be complete, a closing bracket or a
    comma between values, then closes whatever is still open.

    Two properties make this safe to run on a model's answer. It never writes a
    value, so the worst it can do is drop fields, never invent one. And it only
    cuts at a boundary outside a string, so a comma or a brace inside a value
    cannot be mistaken for the end of a field.

    It runs only after normal parsing has already failed, so when it fails too
    the caller raises the same error it would have raised anyway.
    """
    depth: list[str] = []
    in_string = False
    escaped = False
    last_complete = None

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth.append("}" if char == "{" else "]")
        elif char in "}]":
            if depth:
                depth.pop()
            last_complete = index + 1
        elif char == "," and depth:
            last_complete = index

    if last_complete is None:
        return None

    head = text[:last_complete]
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in head:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]" and stack:
            stack.pop()

    return head + "".join(reversed(stack))


def extract_json_object(raw: str) -> dict[str, Any]:
    """Parse the model's answer, ignoring a code fence or surrounding prose."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        text = text.removeprefix("json").strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as first_error:
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else None
        try:
            parsed = json.loads(candidate) if candidate else None
        except json.JSONDecodeError:
            parsed = None

        if parsed is None:
            repaired = close_truncated(text[start:] if start != -1 else text)
            if repaired is None:
                raise LLMResponseError(
                    f"no JSON object in the model's answer: {raw[:200]!r}"
                ) from first_error
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as exc:
                raise LLMResponseError(f"unparseable JSON from the model: {exc}") from exc
            logger.warning(
                "the model's answer was cut off; kept the %d complete field(s) before the cut",
                len(parsed) if isinstance(parsed, dict) else 0,
            )

    if not isinstance(parsed, dict):
        raise LLMResponseError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed
