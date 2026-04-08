"""PDF template preparation abstraction.

Why this exists:
- `commonforms` pulls in heavy runtime deps (ultralytics -> cv2 -> numpy).
- In minimal/server environments this can hard-crash the interpreter during import.
- FireForm only needs `commonforms.prepare_form()` for template creation.

This module provides a safe wrapper that:
- imports `commonforms` lazily (only when template creation is requested)
- raises a clear Python exception instead of crashing at app import time
"""

from __future__ import annotations

from typing import Protocol


class TemplatePreparer(Protocol):
    def __call__(self, input_pdf_path: str, output_pdf_path: str) -> None:
        ...


def prepare_form_safe(input_pdf_path: str, output_pdf_path: str) -> None:
    """Prepare a PDF template using `commonforms` via a lazy import.

    Raises:
        RuntimeError: if `commonforms` cannot be imported or fails at runtime.
    """

    try:
        from commonforms import prepare_form as _prepare_form  # type: ignore
    except Exception as e:  # pragma: no cover
        # Catch broad exceptions because some environments segfault or raise
        # low-level import errors when image dependencies are missing.
        raise RuntimeError(
            "Failed to import `commonforms`. Template creation requires the optional "
            "commonforms + OpenCV runtime dependencies. "
            "If running in Docker, ensure libgl1/libglib2.0-0 are installed."
        ) from e

    try:
        _prepare_form(input_pdf_path, output_pdf_path)
    except Exception as e:
        raise RuntimeError(
            f"Template preparation failed for '{input_pdf_path}'."
        ) from e
