"""The parts of extraction that need no model at all.

Deployment context (timezone, country, currency) and anything arithmetic. The
model is told the context so it can resolve "yesterday evening" itself, and
these functions then fill what it left blank and compute what is derivable:
default country and currency, a timezone offset on naive timestamps, and the
per-unit turnout and travel seconds. Plain code beats a prompt every time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.api.schemas.extraction import ExtractionDefaults, ExtractionHints
from app.core.config import DEFAULT_COUNTRY, DEFAULT_CURRENCY, DEFAULT_TIMEZONE
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExtractionContext:
    """Deployment context for one extraction run."""

    country: str
    timezone: str
    currency: str
    now: datetime

    @property
    def zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("unknown timezone %s, falling back to UTC", self.timezone)
            return ZoneInfo("UTC")


def resolve_context(defaults: ExtractionDefaults | dict | None) -> ExtractionContext:
    """Merge the request's defaults over the server's configured ones."""
    if isinstance(defaults, ExtractionDefaults):
        defaults = defaults.model_dump(exclude_none=True)
    values = defaults or {}
    timezone_name = values.get("timezone") or DEFAULT_TIMEZONE
    context = ExtractionContext(
        country=values.get("country") or DEFAULT_COUNTRY,
        timezone=timezone_name,
        currency=values.get("currency") or DEFAULT_CURRENCY,
        now=datetime.now(),
    )
    return ExtractionContext(
        country=context.country,
        timezone=context.timezone,
        currency=context.currency,
        now=datetime.now(context.zone),
    )


def context_lines(context: ExtractionContext, hints: ExtractionHints | dict | None = None) -> list[str]:
    """The context block every chunk prompt carries in its dynamic tail."""
    lines = [
        f"Right now it is {context.now.isoformat(timespec='seconds')} "
        f"({context.now.strftime('%A')}), timezone {context.timezone}. "
        "Resolve relative times like 'yesterday evening' against it.",
        f"Country when the narrative names none: {context.country}.",
        f"Currency for money amounts when the narrative names none: {context.currency}.",
    ]
    if isinstance(hints, ExtractionHints):
        hints = hints.model_dump(exclude_none=True)
    for key, value in (hints or {}).items():
        if value:
            lines.append(f"Hint from the responder, {key.replace('_', ' ')}: {value}.")
    return lines


def _localize_datetimes(node: Any, context: ExtractionContext) -> Any:
    """Attach the deployment offset to any timestamp the model left naive."""
    if isinstance(node, dict):
        return {key: _localize_datetimes(value, context) for key, value in node.items()}
    if isinstance(node, list):
        return [_localize_datetimes(item, context) for item in node]
    if isinstance(node, str) and len(node) >= 16 and "T" in node:
        try:
            parsed = datetime.fromisoformat(node.replace("Z", "+00:00"))
        except ValueError:
            return node
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=context.zone).isoformat()
    return node


def _apply_currency(node: Any, currency: str) -> Any:
    """Stamp the default currency on Money objects that came back without one."""
    if isinstance(node, dict):
        filled = {key: _apply_currency(value, currency) for key, value in node.items()}
        if isinstance(filled.get("amount"), (int, float)) and not filled.get("currency"):
            filled["currency"] = currency
        return filled
    if isinstance(node, list):
        return [_apply_currency(item, currency) for item in node]
    return node


def _prune_empty(node: Any) -> Any:
    """Drop empty strings and empty containers from a contract document.

    Models answer a field they know nothing about with "" or [] rather than
    leaving it out. In the contract an absent field means unknown, while an
    empty string is a claim that the value is blank, so these are dropped.
    Zero is kept: a count of zero is a real answer.
    """
    if isinstance(node, dict):
        cleaned = {}
        for key, value in node.items():
            pruned = _prune_empty(value)
            if pruned is None or pruned == "" or pruned == [] or pruned == {}:
                continue
            cleaned[key] = pruned
        return cleaned
    if isinstance(node, list):
        items = [_prune_empty(item) for item in node]
        return [item for item in items if item not in (None, "", [], {})]
    return node


def _seconds_between(start: Any, end: Any) -> int | None:
    """Whole seconds between two RFC 3339 strings, or None if that makes no sense."""
    try:
        first = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        second = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if first.tzinfo is None or second.tzinfo is None:
        return None
    delta = (second - first).total_seconds()
    return int(delta) if delta >= 0 else None


def _derive_unit_timings(contract: dict) -> None:
    """Compute each unit's turnout and travel seconds from its own timestamps.

    Arithmetic is not the model's job. When both timestamps are there the
    computed value wins, because models do state a duration that contradicts
    the times they just gave. The model's number is only kept when the
    timestamps are missing and there is nothing to compute from.
    """
    units = contract.get("units")
    if not isinstance(units, list):
        return
    for unit in units:
        if not isinstance(unit, dict):
            continue
        turnout = _seconds_between(unit.get("dispatched_datetime"), unit.get("enroute_datetime"))
        if turnout is not None:
            unit["turnout_seconds"] = turnout
        travel = _seconds_between(unit.get("enroute_datetime"), unit.get("arrived_datetime"))
        if travel is not None:
            unit["travel_seconds"] = travel


def apply_context(contract: dict, context: ExtractionContext) -> dict:
    """Run every deterministic post-step over a stitched contract."""
    filled = _prune_empty(contract)
    filled = _localize_datetimes(filled, context)
    filled = _apply_currency(filled, context.currency)

    # Country is deployment truth, not a guess, so it is stamped even when the
    # narrative said nothing about where it happened.
    location = filled.setdefault("location", {})
    if isinstance(location, dict) and not location.get("country"):
        location["country"] = context.country

    incident = filled.get("incident")
    if isinstance(incident, dict) and not incident.get("timezone"):
        incident["timezone"] = context.timezone

    _derive_unit_timings(filled)
    return filled
