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
        # Generate dictionary of answers from your original function
        t2j = llm.main_loop()
        textbox_answers = t2j.get_data()  # This is a dictionary

        # --- NEW: SEVERITY FILENAME LOGIC ---
        is_urgent = textbox_answers.get("SEVERITY_FLAG") == "HIGH"
        prefix = "URGENT_" if is_urgent else ""
        
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + prefix
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        # Build answers_list, safely ignoring our internal SEVERITY_FLAG
        answers_list = []
        for key, val in textbox_answers.items():
            if key != "SEVERITY_FLAG":
                answers_list.append(val)
        # ------------------------------------

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
