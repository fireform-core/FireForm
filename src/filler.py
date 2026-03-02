from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form using values extracted by the LLM.

        Contract:
            - ``llm._transcript_text`` must be set by the caller before passing
              the LLM instance here.
            - ``llm._target_fields`` must be set by the caller before passing
              the LLM instance here.
            - Extraction is triggered internally via ``main_loop_batch()``,
              which falls back to the sequential ``main_loop()`` if the model
              returns invalid JSON.
            - Fields are filled top-to-bottom, left-to-right based on their
              position in the PDF (sorted by Rect coordinates).

        :param pdf_form:  Absolute or relative path to the fillable PDF template.
        :param llm:       A configured :class:`~src.llm.LLM` instance with
                          ``_transcript_text`` and ``_target_fields`` set.
        :returns:         Path to the newly written filled PDF file.
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
