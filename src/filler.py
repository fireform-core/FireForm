from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime
from typing import Any


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values from user_input using LLM.
        Fields are filled in the visual order (top-to-bottom, left-to-right).
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        # Generate dictionary of answers from your original function
        t2j = llm.main_loop()
        textbox_answers = t2j.get_data()  # This is a dictionary

        answers_list = list(textbox_answers.values())

        # Read PDF
        pdf = PdfReader(pdf_form)

        # Loop through pages
        for page in pdf.pages:  # type: ignore[operator]
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )

                i = 0
                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        if i < len(answers_list):
                            annot.V = f"{answers_list[i]}"
                            annot.AP = None
                            i += 1
                        else:
                            # Stop if we run out of answers
                            break

        PdfWriter().write(output_pdf, pdf)

        # Your main.py expects this function to return the path
        return output_pdf

    def fill_form_from_record(
        self,
        pdf_form: str,
        incident_record: dict[str, Any],
        template_fields: dict[str, Any],
    ) -> str:
        """Fill a PDF from a pre-extracted incident record.

        This bypasses LLM extraction and maps one structured incident object
        into a specific template's field set.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        ordered_template_fields = list(template_fields.keys())
        normalized_record = {
            self._normalize_key(str(k)): v for k, v in incident_record.items()
        }

        pdf = PdfReader(pdf_form)
        field_index = 0

        for page in pdf.pages:  # type: ignore[operator]
            if not page.Annots:
                continue

            sorted_annots = sorted(
                page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
            )

            for annot in sorted_annots:
                if annot.Subtype != "/Widget" or not annot.T:
                    continue

                pdf_field_name = str(annot.T)[1:-1]
                expected_template_field = (
                    ordered_template_fields[field_index]
                    if field_index < len(ordered_template_fields)
                    else None
                )

                value = self._resolve_value_for_pdf_field(
                    pdf_field_name=pdf_field_name,
                    expected_template_field=expected_template_field,
                    normalized_record=normalized_record,
                )

                annot.V = "" if value is None else f"{value}"
                annot.AP = None
                field_index += 1

        PdfWriter().write(output_pdf, pdf)
        return output_pdf

    @staticmethod
    def _normalize_key(field_name: str) -> str:
        return "".join(ch.lower() for ch in field_name if ch.isalnum())

    def _resolve_value_for_pdf_field(
        self,
        pdf_field_name: str,
        expected_template_field: str | None,
        normalized_record: dict[str, Any],
    ) -> Any:
        pdf_key = self._normalize_key(pdf_field_name)
        if pdf_key in normalized_record:
            return normalized_record[pdf_key]

        if expected_template_field:
            template_key = self._normalize_key(expected_template_field)
            if template_key in normalized_record:
                return normalized_record[template_key]

        return None
