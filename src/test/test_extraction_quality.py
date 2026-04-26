from src.extraction_quality import ExtractionQualityProcessor, MISSING_VALUE_SENTINEL


def test_missing_values_use_single_sentinel():
    processor = ExtractionQualityProcessor()

    value = processor.process("Phone", "-1")

    assert value == MISSING_VALUE_SENTINEL
    report = processor.build_report()
    assert report["missing_sentinel"] == MISSING_VALUE_SENTINEL
    assert report["missing_fields"] == ["Phone"]


def test_plural_values_normalize_to_deduplicated_list():
    processor = ExtractionQualityProcessor()

    value = processor.process("Victims", "Jane Doe; John Doe; Jane Doe")

    assert value == ["Jane Doe", "John Doe"]
    report = processor.build_report()
    assert report["plural_normalized_fields"] == ["Victims"]


def test_duplicate_merge_is_deterministic():
    processor = ExtractionQualityProcessor()

    existing = processor.process("Officer", "Alvarez")
    merged = processor.process("Officer", "Alvarez", existing_value=existing)

    assert merged == "Alvarez"
    report = processor.build_report()
    assert report["duplicate_fields"] == ["Officer"]


def test_duplicate_merge_promotes_to_list_when_values_differ():
    processor = ExtractionQualityProcessor()

    existing = processor.process("Officer", "Alvarez")
    merged = processor.process("Officer", "Martinez", existing_value=existing)

    assert merged == ["Alvarez", "Martinez"]


def test_ambiguous_values_are_flagged_for_review():
    processor = ExtractionQualityProcessor()

    processor.process("Incident Type", "Fire or smoke event")

    report = processor.build_report()
    assert report["ambiguous_fields"] == ["Incident Type"]
