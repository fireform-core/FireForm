from src.extraction_quality import ExtractionQualityProcessor, MISSING_VALUE_SENTINEL
from src.llm import LLM


def test_missing_values_use_consistent_sentinel():
    processor = ExtractionQualityProcessor()

    value = processor.process("Phone", "-1")

    assert value == MISSING_VALUE_SENTINEL
    report = processor.build_report()
    assert report["missing_sentinel"] == MISSING_VALUE_SENTINEL
    assert report["missing_fields"] == ["Phone"]


def test_plural_values_are_normalized_and_deduplicated():
    processor = ExtractionQualityProcessor()

    value = processor.process("Victims", "Jane Doe; John Doe; Jane Doe")

    assert value == ["Jane Doe", "John Doe"]
    assert processor.build_report()["plural_normalized_fields"] == ["Victims"]


def test_duplicate_merge_is_deterministic():
    processor = ExtractionQualityProcessor()

    first = processor.process("Officer", "Alvarez")
    merged = processor.process("Officer", "Alvarez", existing_value=first)

    assert merged == "Alvarez"
    assert processor.build_report()["duplicate_fields"] == ["Officer"]


def test_ambiguity_is_flagged_for_review():
    processor = ExtractionQualityProcessor()

    processor.process("Incident Type", "Fire or smoke event")

    assert processor.build_report()["ambiguous_fields"] == ["Incident Type"]


def test_llm_add_response_uses_quality_pipeline():
    llm = LLM()

    llm.add_response_to_json("Victims", "Jane Doe; John Doe; Jane Doe")
    llm.add_response_to_json("Victims", "John Doe")
    llm.add_response_to_json("Phone", "-1")

    data = llm.get_data()
    report = llm.get_quality_report()

    assert data["Victims"] == ["Jane Doe", "John Doe"]
    assert data["Phone"] == MISSING_VALUE_SENTINEL
    assert report["plural_normalized_fields"] == ["Victims"]
