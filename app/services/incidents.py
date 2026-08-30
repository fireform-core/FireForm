"""Incident analytics recompute.

`promote` is the single function that derives the promoted analytics columns
from the incident contract. The routes and the async worker both call it after
any change to the contract, so the columns can never drift from the document
they are derived from. It takes a plain contract dict and returns a plain dict
of column values; it never touches the database.
"""

from datetime import datetime
from typing import Any

# Keys of the value dict returned by ``promote``. Kept explicit so callers can
# apply the result to an Incident row without guessing field names.
PROMOTED_COLUMNS = (
    "incident_name",
    "incident_type",
    "incident_category",
    "incident_datetime",
    "city",
    "state",
    "country",
    "civilian_injuries",
    "civilian_fatalities",
    "responder_injuries",
    "responder_fatalities",
    "people_rescued",
    "people_evacuated",
    "structures_destroyed",
    "area_burned_ha",
    "total_loss_amount",
    "total_loss_currency",
    "call_to_arrival_seconds",
    "turnout_seconds_first_unit",
    "travel_seconds_first_unit",
    "on_scene_duration_seconds",
)


def _obj(contract: dict, key: str) -> dict:
    """Return contract[key] if it is a dict, else an empty dict."""
    value = contract.get(key)
    return value if isinstance(value, dict) else {}


def _parse_dt(value: Any) -> datetime | None:
    """Parse an RFC 3339 date-time string; return None if absent or unparseable."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        # fromisoformat handles the 'Z' suffix from Python 3.11 onwards.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds_between(start: Any, end: Any) -> int | None:
    """Whole seconds from start to end; None unless both parse and end >= start."""
    a = _parse_dt(start)
    b = _parse_dt(end)
    if a is None or b is None:
        return None
    delta = (b - a).total_seconds()
    if delta < 0:
        return None
    return int(delta)


def _primary_type(incident: dict) -> dict:
    """The incident type flagged primary, else the first one, else empty.

    Both `incident_category` and `incident_type` come off this single entry, so
    they can never describe two different types.
    """
    types = incident.get("types")
    if not isinstance(types, list):
        return {}
    entries = [t for t in types if isinstance(t, dict)]
    if not entries:
        return {}
    for entry in entries:
        if entry.get("primary"):
            return entry
    return entries[0]


def _incident_datetime(incident: dict, dispatch: dict) -> datetime | None:
    """Alarm, else start, else dispatch call-received, parsed to a datetime."""
    raw = (
        incident.get("alarm_datetime")
        or incident.get("start_datetime")
        or dispatch.get("call_received_datetime")
    )
    return _parse_dt(raw)


def _total_loss(losses: dict) -> tuple[float | None, str | None]:
    """Sum property and contents loss; currency from whichever is present first."""
    prop = losses.get("property_loss") if isinstance(losses.get("property_loss"), dict) else {}
    contents = losses.get("contents_loss") if isinstance(losses.get("contents_loss"), dict) else {}
    amounts = [v for v in (prop.get("amount"), contents.get("amount")) if isinstance(v, (int, float))]
    total = sum(amounts) if amounts else None
    currency = prop.get("currency") or contents.get("currency")
    return total, currency


def _first_unit(contract: dict) -> dict:
    """The unit that arrived first (earliest arrived_datetime), else empty."""
    units = contract.get("units")
    if not isinstance(units, list):
        return {}
    arrived = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        at = _parse_dt(unit.get("arrived_datetime"))
        if at is not None:
            arrived.append((at, unit))
    if not arrived:
        return {}
    arrived.sort(key=lambda pair: pair[0])
    return arrived[0][1]


def _unit_turnout(unit: dict) -> int | None:
    """Precomputed turnout_seconds, else dispatched to enroute."""
    precomputed = unit.get("turnout_seconds")
    if isinstance(precomputed, int):
        return precomputed
    return _seconds_between(unit.get("dispatched_datetime"), unit.get("enroute_datetime"))


def _unit_travel(unit: dict) -> int | None:
    """Precomputed travel_seconds, else enroute to arrived."""
    precomputed = unit.get("travel_seconds")
    if isinstance(precomputed, int):
        return precomputed
    return _seconds_between(unit.get("enroute_datetime"), unit.get("arrived_datetime"))


def _count(rescues: Any) -> int | None:
    """Number of entries in a list field, or None when it is absent."""
    return len(rescues) if isinstance(rescues, list) else None


def promote(contract: dict | None) -> dict[str, Any]:
    """Derive the promoted analytics columns from the incident contract.

    Every value is nullable; an empty or partial contract yields None for the
    fields it does not cover. This is the only place these columns are computed.
    """
    contract = contract or {}
    incident = _obj(contract, "incident")
    dispatch = _obj(contract, "dispatch")
    location = _obj(contract, "location")
    casualties = _obj(contract, "casualties")
    evacuation = _obj(contract, "evacuation_displacement")
    structure = _obj(contract, "structure")
    wildland = _obj(contract, "wildland")
    losses = _obj(contract, "losses")

    total_loss_amount, total_loss_currency = _total_loss(losses)

    call_received = dispatch.get("call_received_datetime") or incident.get("alarm_datetime")
    first_arrival = incident.get("first_arrival_datetime")
    first_unit = _first_unit(contract)
    primary_type = _primary_type(incident)

    return {
        "incident_name": incident.get("name"),
        "incident_type": primary_type.get("subcategory"),
        "incident_category": primary_type.get("category"),
        "incident_datetime": _incident_datetime(incident, dispatch),
        "city": location.get("city"),
        "state": location.get("state"),
        "country": location.get("country"),
        "civilian_injuries": casualties.get("total_civilian_injuries"),
        "civilian_fatalities": casualties.get("total_civilian_fatalities"),
        "responder_injuries": casualties.get("total_responder_injuries"),
        "responder_fatalities": casualties.get("total_responder_fatalities"),
        "people_rescued": _count(contract.get("rescues")),
        "people_evacuated": evacuation.get("total_people_evacuated"),
        "structures_destroyed": structure.get("structures_destroyed"),
        "area_burned_ha": wildland.get("area_burned_ha"),
        "total_loss_amount": total_loss_amount,
        "total_loss_currency": total_loss_currency,
        "call_to_arrival_seconds": _seconds_between(call_received, first_arrival),
        "turnout_seconds_first_unit": _unit_turnout(first_unit),
        "travel_seconds_first_unit": _unit_travel(first_unit),
        "on_scene_duration_seconds": _seconds_between(first_arrival, incident.get("cleared_datetime")),
    }
