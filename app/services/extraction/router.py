"""Chunk routing.

Deciding what not to ask the model is most of the speed. Core chunks apply to
every incident and always run. Gated chunks only run when their trigger words
appear in the narrative, so a structure fire never pays for the wildland
prompt. Background chunks run last. Nothing here calls the model.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.services.extraction.registry import ChunkSpec, Tier, extractable_chunks

logger = get_logger(__name__)


def select_chunks(text: str) -> list[ChunkSpec]:
    """The chunks worth extracting from this text, in the order to run them.

    Order is tier first (core, then gated, then background) and priority
    within a tier, which the registry already applies.
    """
    selected: list[ChunkSpec] = []
    skipped: list[str] = []

    for spec in extractable_chunks():
        if spec.tier is Tier.gated and not spec.matches(text):
            skipped.append(spec.name)
            continue
        selected.append(spec)

    logger.info(
        "chunk router selected %d chunks (%s), skipped %d gated (%s)",
        len(selected),
        ", ".join(spec.name for spec in selected),
        len(skipped),
        ", ".join(skipped),
    )
    return selected
