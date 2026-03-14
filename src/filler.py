from typing import Any, Optional

from pdfrw import PdfReader, PdfWriter
from src.semantic_mapper import SemanticMapper
from datetime import datetime


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: Any, template_config: Optional[dict] = None):
        """
        Fill a PDF form with values extracted by LLM.

        Fields are matched semantically (JSON key ↔ PDF widget name) first.
        Any unmatched fields fall back to visual-order positional assignment
        (top-to-bottom, left-to-right).

        Parameters
        ----------
        pdf_form        : path to the input PDF template
        llm             : configured LLM instance (main_loop not yet called)
        template_config : optional per-template mapping hints, e.g.
                          {
                            "field_mappings": {"Employee's name": "EmployeeName"},
                            "aliases":        {"Employee's name": ["name"]},
                            "required_fields": ["Employee's name", "Date"]
                          }
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        # ── 1. Extract structured data from LLM ──────────────────────────────
        t2j = llm.main_loop()
        textbox_answers = t2j.get_data()  # {json_key: value}

        # ── 2. Collect PDF widgets in visual order (global across pages) ──────
        pdf = PdfReader(pdf_form)
        ordered_annots = []
        pdf_field_names = []

        for page in (pdf.pages or []):  # type: ignore[operator]
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )
                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        # pdfrw wraps field names in parens: e.g. '(EmployeeName)'
                        pdf_field_names.append(annot.T[1:-1])
                        ordered_annots.append(annot)

        # ── 3. Semantic mapping ───────────────────────────────────────────────
        mapper = SemanticMapper(template_config)
        result = mapper.map(textbox_answers, pdf_field_names)
        print(result.report())

        # ── 4. Fill: semantic matches first, positional fallback for the rest ─
        positional_idx = 0
        for annot, pdf_field in zip(ordered_annots, pdf_field_names):
            if pdf_field in result.matched:
                annot.V = f"{result.matched[pdf_field]}"
                annot.AP = None
            elif positional_idx < len(result.positional_values):
                annot.V = f"{result.positional_values[positional_idx]}"
                annot.AP = None
                positional_idx += 1

        PdfWriter().write(output_pdf, pdf)
        return output_pdf
