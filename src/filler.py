from pdfrw import PdfReader, PdfWriter, PdfName
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
                            val = str(answers_list[i])
                            
                            # CHECKBOX / RADIO BUTTON LOGIC
                            if annot.FT == "/Btn":
                                if val == "Yes":
                                    # Set both value and Appearance State to 'Yes' or 'On'
                                    # Most PDFs use /Yes, but some use /On. /Yes is the safest default.
                                    annot.V = PdfName("Yes")
                                    annot.AS = PdfName("Yes")
                                else:
                                    annot.V = PdfName("Off")
                                    annot.AS = PdfName("Off")
                            
                            # STANDARD TEXT BOX LOGIC
                            else:
                                annot.V = f"{val}"
                                annot.AP = None  # Refresh appearance for text
                            
                            i += 1
                        else:
                            break

        PdfWriter().write(output_pdf, pdf)

        # Your main.py expects this function to return the path
        return output_pdf
