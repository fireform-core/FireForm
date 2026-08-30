"""The chunk registry.

The incident contract is the source of truth for how each of its top-level
chunks is extracted. Every chunk carries `x-extraction` (core, gated,
background or manual), gated chunks carry `x-triggers`, and any chunk can carry
`x-extraction-priority`. This module reads those at import time and pairs each
chunk with the generated Pydantic model that validates it, so the rest of the
worker never hardcodes a chunk name or a tier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, get_args, get_origin

import yaml
from pydantic import BaseModel

from app.api.schemas.incident_contract import IncidentContract
from app.core.config import INCIDENT_CONTRACT_PATH
from app.core.logging import get_logger

logger = get_logger(__name__)


class Tier(str, Enum):
    """What the worker does with a chunk.

    core       always extracted, no gating
    gated      extracted only when the narrative shows evidence for it
    background extracted after everything else, never blocks a form
    manual     never sent to the model (record ids, signatures, reflections)
    """

    core = "core"
    gated = "gated"
    background = "background"
    manual = "manual"


@dataclass(frozen=True)
class ChunkSpec:
    """One top-level contract chunk and everything needed to extract it."""

    name: str
    tier: Tier
    model: type[BaseModel] | None
    is_list: bool
    priority: int = 100
    triggers: tuple[str, ...] = ()
    description: str = ""
    trigger_pattern: re.Pattern[str] | None = field(default=None, compare=False)

    def matches(self, text: str) -> bool:
        """True when the text carries evidence this chunk applies."""
        if self.trigger_pattern is None:
            return False
        return self.trigger_pattern.search(text) is not None


def _build_trigger_pattern(triggers: tuple[str, ...]) -> re.Pattern[str] | None:
    """One case-insensitive word-boundary pattern for a chunk's trigger list."""
    if not triggers:
        return None
    alternatives = "|".join(re.escape(t) for t in sorted(triggers, key=len, reverse=True))
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


def _unwrap(annotation: Any) -> tuple[type[BaseModel] | None, bool]:
    """Reduce a generated field annotation to (model, is_list).

    Generated fields are Optional and sometimes list-valued, so this peels off
    Optional and list wrappers to find the BaseModel underneath. Returns
    (None, False) for scalar chunks like schema_version.
    """
    is_list = False
    seen: list[Any] = [annotation]
    while seen:
        current = seen.pop()
        if isinstance(current, type) and issubclass(current, BaseModel):
            return current, is_list
        origin = get_origin(current)
        if origin is list:
            is_list = True
        args = [arg for arg in get_args(current) if arg is not type(None)]
        seen.extend(args)
    return None, is_list


@lru_cache(maxsize=1)
def _contract_properties() -> dict[str, dict]:
    """The IncidentContract property map, read from the contract file once."""
    doc = yaml.safe_load(INCIDENT_CONTRACT_PATH.read_text())
    return doc["IncidentContract"]["properties"]


@lru_cache(maxsize=1)
def chunk_registry() -> dict[str, ChunkSpec]:
    """Every top-level chunk, keyed by name, in tier and priority order."""
    specs: list[ChunkSpec] = []
    for name, spec in _contract_properties().items():
        tier_value = spec.get("x-extraction")
        if tier_value is None:
            # A chunk with no x-extraction is new and unrouted. Treat it as
            # manual so the worker never silently prompts for something the
            # contract has not classified.
            tier_value = Tier.manual.value
        info = IncidentContract.model_fields.get(name)
        if info is None:
            # The contract grew a chunk the committed models do not have yet.
            # Skip it rather than crash, and say so: the fix is to regenerate.
            logger.warning(
                "contract chunk %s has no generated model, skipping it. "
                "Run `make generate-contract-models`.",
                name,
            )
            continue
        triggers = tuple(spec.get("x-triggers") or ())
        model, is_list = _unwrap(info.annotation)
        specs.append(
            ChunkSpec(
                name=name,
                tier=Tier(tier_value),
                model=model,
                is_list=is_list,
                priority=int(spec.get("x-extraction-priority", 100)),
                triggers=triggers,
                description=(spec.get("description") or "").strip(),
                trigger_pattern=_build_trigger_pattern(triggers),
            )
        )

    tier_order = {Tier.core: 0, Tier.gated: 1, Tier.background: 2, Tier.manual: 3}
    specs.sort(key=lambda s: (tier_order[s.tier], s.priority, s.name))
    return {spec.name: spec for spec in specs}


def extractable_chunks() -> list[ChunkSpec]:
    """Chunks the model can be asked about: everything but manual, and only
    those the generated models can validate."""
    return [
        spec
        for spec in chunk_registry().values()
        if spec.tier is not Tier.manual and spec.model is not None
    ]
