from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime
from src.validation import validate_extraction

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

    # Generate dictionary of answers
    t2j = llm.main_loop()
    raw_data = t2j.get_data()

    # Validation step (separate concern ✅)
    validated_data, errors = validate_extraction(raw_data)

    if errors:
        print("[Validation Warning]", errors)

    textbox_answers = validated_data
    answers_list = list(textbox_answers.values())

    # Read PDF
    pdf = PdfReader(pdf_form)

    # Loop through pages
    i = 0
    for page in pdf.pages:
        if page.Annots:
            sorted_annots = sorted(
                page.Annots,
                key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
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
