"""Round-trip tests for the generated incident-contract models.

These guard the generator's contract: every field is optional, the shared
enums are the ones from app/api/schemas/enums.py (not regenerated copies), and
a contract dict survives validate -> dump -> validate unchanged.
"""

from app.api.schemas import enums
from app.api.schemas.incident_contract import IncidentContract, IncidentType

SAMPLE = {
    "schema_version": "1.1.0",
    "schema_name": "fireform_incident_contract",
    "incident": {
        "name": "Warehouse fire",
        "types": [{"primary": True, "category": "natural_disaster"}],
    },
    "casualties": {"civilian": [{"severity": "life_threatening"}]},
}


def test_empty_contract_validates():
    """Absent field means unknown, so an empty document is valid."""
    model = IncidentContract.model_validate({})
    assert model.model_dump(exclude_none=True) == {}


def test_sample_round_trips():
    model = IncidentContract.model_validate(SAMPLE)
    dumped = model.model_dump(exclude_none=True, mode="json")

    # exclude_none keeps only what was actually filled.
    assert dumped == SAMPLE
    assert "dispatch" not in dumped

    # Re-validating the dump gives an equal model.
    assert IncidentContract.model_validate(dumped) == model


def test_shared_enums_are_reused():
    """The models import the existing enums instead of defining new copies."""
    assert IncidentType.model_fields["category"].annotation.__args__[0] is enums.IncidentCategory


def test_contract_synced_enum_members():
    """Members added to the contract are reachable through the reused enum."""
    model = IncidentContract.model_validate(SAMPLE)
    assert model.incident.types[0].category is enums.IncidentCategory.natural_disaster
    assert model.casualties.civilian[0].severity is enums.InjurySeverity.life_threatening
