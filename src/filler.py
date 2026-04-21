from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from src.zip_resolver import OfflineUSZipResolver
from datetime import datetime


class Filler:
    def __init__(self):
        self.zip_resolver = OfflineUSZipResolver()

    def _fill_pdf_with_answers(self, pdf_form: str, textbox_answers: dict):
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        textbox_answers = self.zip_resolver.enrich_missing_zip_fields(textbox_answers)
        answers_list = list(textbox_answers.values())

        pdf = PdfReader(pdf_form)
        i = 0
        for page in pdf.pages:
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )

                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        if i < len(answers_list):
                            annot.V = f"{answers_list[i]}"
                            annot.AP = None
                            i += 1
                        else:
                            break

        PdfWriter().write(output_pdf, pdf)
        return output_pdf

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values from user_input using LLM.
        Fields are filled in the visual order (top-to-bottom, left-to-right).
        """
        # Backwards-compatible wrapper used by old call sites.
        t2j = llm.main_loop()
        return self._fill_pdf_with_answers(pdf_form=pdf_form, textbox_answers=t2j.get_data())

    def fill_form_with_answers(self, pdf_form: str, answers: dict):
        return self._fill_pdf_with_answers(pdf_form=pdf_form, textbox_answers=answers)
