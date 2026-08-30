from app.api.schemas.enums import FieldSource


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
