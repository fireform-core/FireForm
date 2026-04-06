from pdfrw import PdfReader, PdfWriter, PdfDict, PdfObject
from src.llm import LLM
from src.pdf_utils import decode_pdf_name
from datetime import datetime
import uuid


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
            + str(uuid.uuid4())
            + "_filled.pdf"
        )

        # Generate dictionary of answers from your original function
        t2j = llm.main_loop()
        textbox_answers = t2j.get_data()  # This is a dictionary

        answers_list = list(textbox_answers.values())

        # Read PDF
        pdf = PdfReader(pdf_form)

        # Global index across all pages (visual order is per page, pages in document order).
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

        # Your main.py expects this function to return the path
        return output_pdf


    def fill_form_by_name(self, pdf_form: str, field_values: dict[str, str]) -> str:
        """
        Fill a PDF form with values from a dictionary mapped by field name.
        Unlike `fill_form`, this does not rely on visual ordering, it relies on
        the exact field name defined in the PDF template matching a key in `field_values`.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + str(uuid.uuid4())
            + "_filled.pdf"
        )

        # Read PDF
        pdf = PdfReader(pdf_form)

        # Force generation of Appearance Streams so text is visible in standard viewers
        if pdf.Root.AcroForm:
            pdf.Root.AcroForm.update(PdfDict(NeedAppearances=PdfObject('true')))

        # Loop through pages
        for page in pdf.pages:
            if page.Annots:
                for annot in page.Annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        field_name = decode_pdf_name(str(annot.T).strip("() /"))
                        
                        if field_name in field_values:
                            # Update the PDF annotation
                            annot.V = f"{field_values[field_name]}"
                            annot.AP = None

        PdfWriter().write(output_pdf, pdf)
        return output_pdf
