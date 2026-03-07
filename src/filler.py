from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from pathlib import Path
from uuid import uuid4


class Filler:
    def __init__(self):
        pass

    @staticmethod
    def _make_output_path(pdf_form: str) -> str:
        """
        Generate a unique output path for a filled PDF.

        Previously this used datetime.now().strftime("%Y%m%d_%H%M%S"), which has
        only 1-second resolution. Two concurrent requests for the same template
        within the same second would produce identical paths, causing the second
        write to silently overwrite the first and corrupting the first submission's
        stored record.

        uuid4().hex provides 128 bits of randomness — collision probability is
        effectively zero (2^-128) regardless of concurrency or timing.

        Output is written to an `outputs/` subdirectory next to the template so
        that generated files are cleanly separated from source templates.
        """
        template_path = Path(pdf_form)
        output_dir = template_path.parent / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / f"{template_path.stem}_{uuid4().hex}_filled.pdf")

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values from user_input using LLM.
        Fields are filled in the visual order (top-to-bottom, left-to-right).
        """
        output_pdf = self._make_output_path(pdf_form)

        # Generate dictionary of answers from your original function
        t2j = llm.main_loop()
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
