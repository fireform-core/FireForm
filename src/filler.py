from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime
import re

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
        
        target_keys = ["Employee's name", "Name", "Full Name", "Patient Name"]
        extracted_name = None
        
        for key in target_keys:
            if key in textbox_answers and textbox_answers[key]:
                val = textbox_answers[key]
                # If the LLM returned a list (plural values), grab the first item
                extracted_name = str(val[0]) if isinstance(val, list) else str(val)
                break
                
        # 3. Create the output filename
        if extracted_name and extracted_name != "-1":
            # Clean illegal characters and spaces
            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', extracted_name.replace(' ', '_'))
            safe_name = re.sub(r'_+', '_', safe_name).strip('_')
            output_pdf = f"{pdf_form[:-4]}_{safe_name}.pdf"
        else:
            # Fallback to the original timestamp method if no name is found
            output_pdf = (
                pdf_form[:-4]
                + "_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + "_filled.pdf"
            )
            
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
