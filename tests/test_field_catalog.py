"""Tests for the incident-contract field catalog and GET /schema/fields.

The catalog is built from contracts/schemas/incident-contract.yaml, so these
assert on fields that have been in the contract since it was written rather
than on exact counts, which move with every schema change.
"""

from app.core.config import API_PREFIX
from app.services import field_catalog

FIELDS_URL = f"{API_PREFIX}/schema/fields"


def _by_path(path):
    return next((e for e in field_catalog.catalog() if e.path == path), None)


# ---------------------------------------------------------------------------
# Building the catalog
# ---------------------------------------------------------------------------
def test_catalog_flattens_nested_objects():
    entry = _by_path("location.postal_code")
    assert entry is not None
    assert entry.section == "location"
    assert entry.field_type == "string"
    assert entry.label == "Postal code"


def test_catalog_marks_array_hops():
    paths = [e.path for e in field_catalog.catalog()]
    assert any(p.startswith("persons_involved[].") for p in paths)


def test_catalog_reads_aliases_from_the_contract():
    entry = _by_path("location.postal_code")
    assert "zip" in entry.aliases


def test_catalog_reads_the_pii_flag():
    pii_paths = [e.path for e in field_catalog.catalog() if e.pii]
    assert pii_paths, "the contract marks several fields x-pii"


def test_catalog_resolves_enum_references():
    with_enums = [e for e in field_catalog.catalog() if e.enum_values]
    assert with_enums, "enum-typed fields should carry their values"


def test_schema_version_comes_from_the_contract():
    assert field_catalog.schema_version()


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def test_exact_name_wins():
    top = field_catalog.search("postal_code", limit=3)[0]
    assert top[0].path == "location.postal_code"
    assert top[1] == 1.0


def test_alias_finds_the_field():
    top = field_catalog.search("zip", limit=3)[0]
    assert top[0].path == "location.postal_code"


def test_an_exact_name_outranks_an_alias():
    entry = _by_path("location.postal_code")
    # score_entry takes an already normalized query, the way search does.
    name_score = field_catalog.score_entry(entry, field_catalog.normalize("postal_code"))
    alias_score = field_catalog.score_entry(entry, "zip")
    assert name_score > alias_score


def test_nonsense_query_returns_nothing():
    assert field_catalog.search("qwertyuiop asdf", limit=5) == []


def test_search_respects_the_limit():
    assert len(field_catalog.search("date", limit=3)) <= 3


def test_listing_returns_the_whole_catalog():
    # The editor caches the catalog and filters locally, so a bare listing
    # must not be truncated by the search limit.
    assert len(field_catalog.search(limit=5)) == len(field_catalog.catalog())


def test_section_filter():
    hits = field_catalog.search(section="location")
    assert hits
    assert {entry.section for entry, _ in hits} == {"location"}


def test_label_normalization_expands_form_shorthand():
    assert field_catalog.normalize_label("Incident No.:") == "incident number"
    assert field_catalog.normalize_label("Dt of Loss") == "date of loss"


# ---------------------------------------------------------------------------
# GET /schema/fields
# ---------------------------------------------------------------------------
def test_endpoint_searches(client):
    resp = client.get(FIELDS_URL, params={"q": "zip", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "zip"
    assert body["schema_version"]
    assert body["total"] == len(body["fields"])
    first = body["fields"][0]
    assert first["path"] == "location.postal_code"
    assert first["score"] > 0
    assert "zip" in first["aliases"]


def test_endpoint_lists_without_a_query(client):
    body = client.get(FIELDS_URL).json()
    assert body["query"] is None
    assert body["total"] > 100
    assert body["fields"][0]["score"] is None


def test_endpoint_filters_by_section(client):
    body = client.get(FIELDS_URL, params={"section": "location"}).json()
    assert {f["section"] for f in body["fields"]} == {"location"}


def test_endpoint_rejects_an_oversized_limit(client):
    assert client.get(FIELDS_URL, params={"q": "date", "limit": 500}).status_code == 422
