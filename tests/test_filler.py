"""
Tests for src/filler.py — specifically the output path generation logic.
"""
import os
from src.filler import Filler


def test_make_output_path_is_unique():
    """
    Every call to _make_output_path() must return a distinct path.

    Previously, paths were generated with a 1-second timestamp, meaning two
    concurrent requests within the same second would produce the same path and
    the second write would silently overwrite the first (race condition).

    With uuid4().hex the collision probability is 2^-128 — effectively zero.
    """
    paths = {Filler._make_output_path("src/inputs/template.pdf") for _ in range(500)}
    assert len(paths) == 500, (
        "Expected 500 unique output paths but got collisions. "
        "The race condition fix may have been reverted."
    )


def test_make_output_path_lands_in_outputs_subdir():
    """
    Output PDFs must be written into an 'outputs/' subdirectory,
    not alongside the source template.
    """
    path = Filler._make_output_path("src/inputs/template.pdf")
    parts = path.replace("\\", "/").split("/")
    assert "outputs" in parts, (
        f"Output path '{path}' does not contain an 'outputs/' directory. "
        "Generated files must be separated from source templates."
    )


def test_make_output_path_extension_is_pdf():
    """Output path must end with .pdf."""
    path = Filler._make_output_path("src/inputs/template.pdf")
    assert path.endswith(".pdf"), f"Expected .pdf extension, got: {path}"


def test_make_output_path_preserves_stem():
    """Output filename must include the original template stem for traceability."""
    path = Filler._make_output_path("src/inputs/my_form.pdf")
    filename = os.path.basename(path)
    assert filename.startswith("my_form_"), (
        f"Expected filename to start with 'my_form_', got: {filename}"
    )
