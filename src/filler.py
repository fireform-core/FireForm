from pdfrw import PdfReader, PdfWriter
from datetime import datetime


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, data: dict) -> str:
        """
        Fill a PDF form with pre-extracted, validated field values.

        Separation of concerns: this class is responsible only for writing
        data to a PDF. LLM extraction and validation are handled upstream
        by FileManipulator before this method is called.

        Fields are written in visual order (top-to-bottom, left-to-right)
        to match the annotation layout of the source PDF.

        Args:
            pdf_form: Absolute or relative path to the fillable PDF template.
            data: Pre-extracted and validated field values. Values are written
                  positionally in the order they appear in the dict.

        Returns:
            Path to the newly written, filled PDF file.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        answers_list = list(data.values())

        pdf = PdfReader(pdf_form)

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
                            break

        PdfWriter().write(output_pdf, pdf)
        return output_pdf
