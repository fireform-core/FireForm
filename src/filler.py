from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime


class Filler:
    def __init__(self):
        pass

    @staticmethod
    def _decode_pdf_field_name(annot_T) -> str:
        """
        pdfrw stores field names as PDF string objects like b'(Employee Name)' or '(date)'.
        This helper strips the surrounding parentheses to get the plain field name string.
        """
        raw = str(annot_T)
        if raw.startswith("(") and raw.endswith(")"):
            return raw[1:-1]
        return raw

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values extracted by the LLM.

        Matching strategy: field-name-based (not positional).

        For every Widget annotation in the PDF we read annot.T (the PDF field name),
        look that name up directly in the LLM-produced answers dict, and write the
        matched value.  This is safe regardless of annotation order because we never
        rely on position/index to pair a value with a field.

        If the PDF field name has no match in the LLM result we leave it blank
        rather than silently writing a wrong value.  Plural answers (lists) are
        joined with '; ' so the field stays human-readable.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        # Run the LLM extraction pipeline → {field_name: value | list | None}
        answers: dict = llm.main_loop().get_data()

        print(f"\t[LOG] Filler received {len(answers)} answer(s) from LLM.")

        # Build a lowercase-keyed lookup so minor capitalisation differences
        # between the stored template and the PDF's own field labels don't block a match.
        normalised_answers = {k.lower().strip(): v for k, v in answers.items()}

        unmatched_pdf_fields = []

        # Read PDF
        pdf = PdfReader(pdf_form)

        for page in pdf.pages:
            if not page.Annots:
                continue

            for annot in page.Annots:
                if annot.Subtype != "/Widget" or not annot.T:
                    continue

                pdf_field_name = self._decode_pdf_field_name(annot.T)
                lookup_key = pdf_field_name.lower().strip()

                if lookup_key in normalised_answers:
                    raw_value = normalised_answers[lookup_key]

                    if raw_value is None:
                        # LLM could not find the value — write empty string, not "None"
                        annot.V = ""
                    elif isinstance(raw_value, list):
                        # Plural values (e.g. multiple engines) → join for readability
                        annot.V = "; ".join(str(v) for v in raw_value if v is not None)
                    else:
                        annot.V = str(raw_value)

                    # Clear the pre-rendered appearance stream so the viewer
                    # re-renders with the new value.
                    annot.AP = None
                else:
                    unmatched_pdf_fields.append(pdf_field_name)

        if unmatched_pdf_fields:
            print(
                f"\t[WARN] {len(unmatched_pdf_fields)} PDF field(s) had no matching "
                f"LLM answer and were left blank: {unmatched_pdf_fields}"
            )

        PdfWriter().write(output_pdf, pdf)
        return output_pdf
