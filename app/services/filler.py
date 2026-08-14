from datetime import datetime

from pdfrw import PdfReader, PdfWriter

from app.services.llm import LLM


def _pdf_text(value) -> str:
    """Decode a pdfrw string (field name / tooltip) to plain text.

    Duplicated from app.services.template._pdf_text — importing it directly
    would create a circular import (template -> controller ->
    file_manipulator -> filler -> template). Keep these in sync: this must
    normalize a widget name exactly the way template.py normalizes it when
    it names the widget, so textbox_answers keys and widget names compare
    equal.
    """
    if value is None:
        return ""
    if hasattr(value, "to_unicode"):
        return value.to_unicode().strip()
    return str(value).strip()


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values from user_input using LLM.
        Each widget is matched to its answer by name (widget name == field-dict
        key, since prepare_fillable names widgets after their field and the LLM
        keys its answers by field name) — not by position, since the field-dict
        order and the PDF's physical widget order aren't guaranteed to match.
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

        # Read PDF
        pdf = PdfReader(pdf_form)

        # Loop through pages
        for page in pdf.pages:
            if page.Annots:
                for annot in page.Annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        name = _pdf_text(annot.T)
                        if name in textbox_answers:
                            annot.V = f"{textbox_answers[name]}"
                            annot.AP = None

        PdfWriter().write(output_pdf, pdf)

        # Your main.py expects this function to return the path
        return output_pdf
