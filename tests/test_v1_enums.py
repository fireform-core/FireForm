from pathlib import Path

import pytest
import yaml

from app.api.schemas import enums
from app.api.schemas.enums import FieldSource

ENUMS_YAML = Path(__file__).resolve().parent.parent / "contracts" / "schemas" / "enums.yaml"
CONTRACT_ENUMS = {
    name: spec["enum"]
    for name, spec in yaml.safe_load(ENUMS_YAML.read_text()).items()
    if "enum" in spec
}


class TestFieldSource:
    def test_members_and_values(self):
        assert FieldSource.schema.value == "schema"
        assert FieldSource.static.value == "static"
        assert FieldSource.manual.value == "manual"
        assert FieldSource.open.value == "open"

    def test_is_str_enum(self):
        assert FieldSource.manual == "manual"
        assert set(FieldSource) == {
            FieldSource.schema,
            FieldSource.static,
            FieldSource.manual,
            FieldSource.open,
        }


class TestEnumsMatchContract:
    """enums.yaml is the source of truth. The generator only checks the enums
    the incident contract pulls in, so this covers the rest (health, job type,
    sort order) and fails on drift instead of letting a status go unchecked."""

    @pytest.mark.parametrize("name", sorted(CONTRACT_ENUMS))
    def test_enums_py_matches_enums_yaml(self, name):
        assert hasattr(enums, name), f"{name} is in enums.yaml but not in enums.py"
        assert [member.value for member in getattr(enums, name)] == CONTRACT_ENUMS[name]
