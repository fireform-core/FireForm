from datetime import datetime

from pdfrw import PdfReader, PdfWriter


class Filler:
    def fill_form(self, pdf_form: str, values: dict[str, str | None]) -> str:
        """Write values into a PDF's form widgets and return the new file's path.

        Widgets are filled in visual order, top to bottom then left to right,
        and the values are consumed in the order they were collected.
        """
        output_pdf = (
            pdf_form[:-4] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_filled.pdf"
        )

        answers = list(values.values())
        pdf = PdfReader(pdf_form)

        i = 0
        for page in pdf.pages:
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )

                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        if i >= len(answers):
                            break
                        annot.V = f"{answers[i]}"
                        annot.AP = None
                        i += 1

        PdfWriter().write(output_pdf, pdf)
        return output_pdf
