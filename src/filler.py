from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime


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

        # Generate dictionary of answers from your original function.
        # main_loop_batch() extracts all fields in a single LLM call instead of
        # one call per field, significantly reducing latency for large forms.
        # Falls back to the sequential main_loop() if the LLM returns invalid JSON.
        t2j = llm.main_loop_batch()
        textbox_answers = t2j.get_data()  # This is a dictionary

        answers_list = list(textbox_answers.values())

        # Read PDF
        pdf = PdfReader(pdf_form)

        # Loop through pages
        for page in pdf.pages:
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

    def fill_form_with_data(self, pdf_form: str, data: dict) -> str:
        """
        Fill a PDF form using a pre-extracted field → value mapping.

        Unlike fill_form(), which calls the LLM itself and fills fields
        positionally, this method accepts an already-extracted ``data`` dict
        and matches values to form annotations by field name (the ``T``
        annotation key). This makes it suitable for the batch pipeline where
        extraction has already happened upstream (canonical pass + mapping
        pass) and only the PDF write step remains.

        Field names that appear in ``data`` but not in the PDF are silently
        skipped. Fields present in the PDF but absent from ``data`` are left
        blank.

        Args:
            pdf_form: Path to the blank PDF template.
            data:     A ``{field_name: value}`` dict as returned by
                      ``IncidentExtractor.async_map_to_template()``.

        Returns:
            Path to the written output PDF.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        pdf = PdfReader(pdf_form)

        for page in pdf.pages:
            if page.Annots:
                for annot in page.Annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        # Strip surrounding parentheses that pdfrw adds to strings
                        field_name = annot.T.strip("()")
                        if field_name in data and data[field_name] is not None:
                            value = data[field_name]
                            if isinstance(value, list):
                                value = ", ".join(str(v) for v in value)
                            annot.V = str(value)
                            annot.AP = None

        PdfWriter().write(output_pdf, pdf)
        return output_pdf

