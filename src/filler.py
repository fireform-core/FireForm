from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pdfrw import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


class Filler:
    """
    Fills a PDF form using a named field mapping produced by TemplateMapper.

    Replaces the old positional approach (answers_list[i]) with an explicit
    {pdf_field_name: value} dict so every value lands in the correct field
    regardless of visual order or page layout.
    """

    def fill_form(self, pdf_form: str, field_values: dict[str, Any]) -> str:
        """
        Write field_values into the PDF at pdf_form and save to a timestamped path.

        Parameters
        ----------
        pdf_form:     Path to the fillable PDF template.
        field_values: {pdf_field_name: value} produced by TemplateMapper.resolve().

        Returns
        -------
        Path to the newly written filled PDF.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        pdf = PdfReader(pdf_form)
        filled_count = 0

        for page in pdf.pages:
            if not page.Annots:
                continue
            for annot in page.Annots:
                if annot.Subtype != "/Widget" or not annot.T:
                    continue

                field_name = self._field_name(annot.T)
                if field_name in field_values:
                    annot.V = str(field_values[field_name])
                    annot.AP = None
                    filled_count += 1
                else:
                    logger.debug("PDF field %r has no mapped value — left blank", field_name)

        logger.info("Filled %d / %d mapped fields in %s", filled_count, len(field_values), pdf_form)
        PdfWriter().write(output_pdf, pdf)
        return output_pdf

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _field_name(annot_t) -> str:
        """
        Extract the plain field name string from a pdfrw PdfString.
        pdfrw wraps PDF literal strings in parentheses, e.g. '(FieldName)'.
        """
        raw = str(annot_t)
        return raw[1:-1] if raw.startswith("(") and raw.endswith(")") else raw
