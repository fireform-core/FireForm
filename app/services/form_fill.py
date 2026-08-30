"""Reading a PDF template's field values out of a narrative.

One prompt per field, which is slow but simple, and it is what the template
fill path has always done. The prompts are answered by the shared LLM module,
so this works against whichever provider the deployment is configured for.

Not to be confused with the extraction layer, which asks about a whole section
of the incident contract at a time. This one only knows about the fields a
particular PDF template happens to have.
"""

from __future__ import annotations

import os

from app.core.logging import get_logger
from app.services import llm

logger = get_logger(__name__)

_NOT_FOUND = "-1"


def _prompt_template() -> str:
    path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    with open(path, "r") as handle:
        return handle.read()


def _clean(answer: str) -> str | None:
    """The model's answer as a value, or None when it found nothing."""
    value = answer.strip().replace('"', "")
    return None if value == _NOT_FOUND else value


def extract_field_values(
    text: str, fields: dict[str, str], model: str | None = None
) -> dict[str, str | None]:
    """Ask for each template field in turn and collect the answers."""
    template = _prompt_template()
    values: dict[str, str | None] = {}

    for index, (field, field_type) in enumerate(fields.items(), 1):
        prompt = template.format(
            field=field,
            type=field_type if isinstance(field_type, str) else "string",
            text=text,
        )
        values[field] = _clean(llm.generate(prompt, model=model))
        logger.info("[%d/%d] extracted %r", index, len(fields), field)

    return values
