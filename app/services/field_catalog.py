"""The incident-contract field catalog and its matcher.

Everything here is built by flattening `contracts/schemas/incident-contract.yaml`
at first use: dotted paths, types, sections, descriptions, enum values, the
`x-pii` flag and the `x-aliases` list. The contract is the only place any of
that is declared, so a schema change moves search and mapping suggestions with
it and nothing is restated in code.

Two callers share this one index: GET /api/v1/schema/fields (the mapping picker
in the template editor) and the suggester that runs after commonforms field
detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

import yaml

from app.core.config import INCIDENT_CONTRACT_PATH
from app.core.logging import get_logger

logger = get_logger(__name__)

_ROOT = "IncidentContract"
_PUNCTUATION = re.compile(r"[^a-z0-9]+")

# Form labels are written for people, not matchers. These are the shortenings
# that show up on nearly every printed incident form.
_ABBREVIATIONS = {
    "no": "number",
    "num": "number",
    "nbr": "number",
    "dt": "date",
    "addr": "address",
    "tel": "phone",
    "ph": "phone",
    "dob": "date of birth",
    "amt": "amount",
    "qty": "quantity",
    "desc": "description",
    "dept": "department",
    "apt": "apartment",
    "st": "street",
    "yr": "year",
    "veh": "vehicle",
    "inj": "injury",
}


@dataclass(frozen=True)
class CatalogEntry:
    """One leaf field of the contract, ready to search."""

    path: str
    label: str
    field_type: str
    section: str
    description: str | None = None
    enum_values: tuple[str, ...] | None = None
    pii: bool = False
    aliases: tuple[str, ...] = ()
    tokens: frozenset[str] = field(default_factory=frozenset, compare=False)


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    return _PUNCTUATION.sub(" ", text.lower()).strip()


def normalize_label(text: str) -> str:
    """Normalize a label read off a PDF, expanding the usual form shorthand.

    Detected labels are messy ("Incident No.:", "Dt of Loss"), so the words are
    expanded before they ever reach the matcher.
    """
    words = normalize(text).split()
    return " ".join(_ABBREVIATIONS.get(word, word) for word in words)


def _humanize(name: str) -> str:
    words = name.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else name


def _tokens(*values: str) -> frozenset[str]:
    out: set[str] = set()
    for value in values:
        out.update(normalize(value).split())
    return frozenset(out)


# ---------------------------------------------------------------------------
# Catalog construction
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _contract_doc() -> dict[str, Any]:
    return yaml.safe_load(INCIDENT_CONTRACT_PATH.read_text())


@lru_cache(maxsize=1)
def _enums_doc() -> dict[str, Any]:
    """The shared enum file the contract points at for closed value lists."""
    enums_path = INCIDENT_CONTRACT_PATH.parent / "enums.yaml"
    try:
        return yaml.safe_load(enums_path.read_text()) or {}
    except OSError:
        logger.warning("enum file %s is missing, enum values will be empty", enums_path)
        return {}


def _resolve(spec: dict[str, Any]) -> dict[str, Any]:
    """Follow a $ref one hop, inside the contract or into enums.yaml.

    Anything the ref does not carry (a description written at the reference
    site, for example) stays, so both halves survive.
    """
    ref = spec.get("$ref")
    if not ref:
        return spec

    file_part, _, name = ref.partition("#/")
    if "enums.yaml" in file_part:
        target = _enums_doc().get(name)
    elif file_part in ("", "#"):
        target = _contract_doc().get(name)
    else:
        target = None

    if not isinstance(target, dict):
        logger.warning("unresolved $ref %s in the incident contract", ref)
        return {k: v for k, v in spec.items() if k != "$ref"}

    merged = dict(target)
    for key, value in spec.items():
        if key != "$ref":
            merged.setdefault(key, value)
    return merged


def _field_type(spec: dict[str, Any]) -> str:
    declared = spec.get("type")
    if isinstance(declared, str):
        return declared
    if spec.get("enum"):
        return "string"
    if spec.get("properties"):
        return "object"
    return "string"


def _walk(
    spec: dict[str, Any],
    path: str,
    section: str,
    name: str,
    seen: frozenset[str],
    out: list[CatalogEntry],
) -> None:
    spec = _resolve(spec)

    properties = spec.get("properties")
    if properties:
        # A recursive shape would otherwise walk forever. Stop the second time
        # the same object type appears on one branch.
        marker = spec.get("title") or path
        if marker in seen:
            return
        seen = seen | {marker}
        for child_name, child_spec in properties.items():
            if not isinstance(child_spec, dict):
                continue
            child_path = f"{path}.{child_name}" if path else child_name
            _walk(child_spec, child_path, section, child_name, seen, out)
        return

    if spec.get("type") == "array":
        items = spec.get("items")
        if isinstance(items, dict):
            resolved = _resolve(items)
            if resolved.get("properties"):
                _walk(items, f"{path}[]", section, name, seen, out)
                return

    enum_values = spec.get("enum")
    out.append(
        CatalogEntry(
            path=path,
            label=_humanize(name),
            field_type=_field_type(spec),
            section=section,
            description=(spec.get("description") or "").strip() or None,
            enum_values=tuple(str(v) for v in enum_values) if enum_values else None,
            pii=bool(spec.get("x-pii")),
            aliases=tuple(spec.get("x-aliases") or ()),
            tokens=_tokens(name, *(spec.get("x-aliases") or ())),
        )
    )


@lru_cache(maxsize=1)
def catalog() -> tuple[CatalogEntry, ...]:
    """Every leaf field in the contract, in contract order."""
    properties = _contract_doc()[_ROOT].get("properties", {})
    entries: list[CatalogEntry] = []
    for section, spec in properties.items():
        if isinstance(spec, dict):
            _walk(spec, section, section, section, frozenset(), entries)
    return tuple(entries)


@lru_cache(maxsize=1)
def schema_version() -> str | None:
    """The contract version the catalog was built from."""
    properties = _contract_doc()[_ROOT].get("properties", {})
    version = properties.get("schema_version") or {}
    example = version.get("example")
    return str(example) if example else None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
# Scores are banded rather than blended, so the ranking the contract describes
# holds no matter how the fuzzy ratio lands: an exact name beats an exact alias,
# both beat a prefix, and a description-only hit always comes last.
_EXACT_NAME = 1.0
_EXACT_ALIAS = 0.95
_NAME_PREFIX = 0.85
_ALIAS_PREFIX = 0.8
_FUZZY_CEILING = 0.75
_FUZZY_FLOOR = 0.6
_DESCRIPTION_HIT = 0.35


def _leaf_name(path: str) -> str:
    return path.rsplit(".", 1)[-1].removesuffix("[]")


def score_entry(entry: CatalogEntry, query: str) -> float:
    """How well one catalog entry answers a query, 0 when it does not.

    `query` is expected already normalized, since `search` normalizes once and
    then scores the whole catalog with it.
    """
    if not query:
        return 0.0

    name = normalize(_leaf_name(entry.path))
    aliases = [normalize(a) for a in entry.aliases]

    if query == name:
        return _EXACT_NAME
    if query in aliases:
        return _EXACT_ALIAS
    if name.startswith(query):
        return _NAME_PREFIX
    if any(alias.startswith(query) for alias in aliases):
        return _ALIAS_PREFIX

    query_tokens = set(query.split())
    if query_tokens and query_tokens <= entry.tokens:
        return _FUZZY_CEILING

    best = max(
        (SequenceMatcher(None, query, candidate).ratio() for candidate in [name, *aliases]),
        default=0.0,
    )
    if best >= _FUZZY_FLOOR:
        return round(best * _FUZZY_CEILING, 4)

    if entry.description and query_tokens:
        description_tokens = set(normalize(entry.description).split())
        if query_tokens <= description_tokens:
            return _DESCRIPTION_HIT

    return 0.0


def search(
    query: str | None = None,
    section: str | None = None,
    limit: int = 20,
) -> list[tuple[CatalogEntry, float | None]]:
    """Rank the catalog against `query`, or list it when no query is given.

    `limit` caps search results only. A bare listing returns the whole catalog,
    because the editor caches it once per session and filters it locally, and a
    truncated catalog would silently hide fields from the mapping picker.

    Ties break toward the shorter path, so the plainest field wins.
    """
    entries = [e for e in catalog() if section is None or e.section == section]

    if not query or not query.strip():
        return [(entry, None) for entry in entries]

    normalized = normalize(query)
    scored = [(entry, score_entry(entry, normalized)) for entry in entries]
    hits = [(entry, score) for entry, score in scored if score > 0]
    hits.sort(key=lambda pair: (-pair[1], len(pair[0].path), pair[0].path))
    return [(entry, score) for entry, score in hits[:limit]]
