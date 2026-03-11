from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with confirmed high-confidence values from the LLM.
        Fields flagged as low-confidence are written with a [REVIEW REQUIRED] placeholder
        so reviewers can easily spot them in the document.

        Returns:
            tuple: (output_pdf_path: str, needs_review: dict)
                   needs_review is a dict of {field_name: {suggested_value, confidence}}
                   that must be presented to the user for manual verification.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        # Run LLM extraction — populates both confirmed and needs_review buckets
        t2j = llm.main_loop()
        confirmed_answers = t2j.get_data()      # high-confidence fields
        needs_review = t2j.get_needs_review()   # low-confidence fields

        # Merge all field names so we can look up values by name
        all_answers = dict(confirmed_answers)
        all_answers.update({
            field: "[REVIEW REQUIRED]"
            for field in needs_review
        })

        # Read PDF
        pdf = PdfReader(pdf_form)

        # Loop through pages and fill by field name (annot.T) not by position
        for page in pdf.pages:
            if page.Annots:
                for annot in page.Annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        # annot.T is a PDF string like "(FieldName)"; strip the parens
                        field_name = str(annot.T).strip("()")
                        if field_name in all_answers:
                            annot.V = str(all_answers[field_name])
                            annot.AP = None

        PdfWriter().write(output_pdf, pdf)

        return output_pdf, needs_review
