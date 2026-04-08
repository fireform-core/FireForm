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
                            answer = answers_list[i]
                            
                            # Check if the field type is a Button (Checkbox/Radio)
                            field_type = annot.FT if annot.FT else (annot.Parent.FT if annot.Parent else None)
                            if str(field_type) == "/Btn":
                                is_truthy = str(answer).lower() in ["yes", "true", "1", "x", "on"]
                                
                                # Find the 'ON' state from the appearance dictionary
                                on_state = "/Yes" # Default assumption
                                if annot.AP and annot.AP.N:
                                    keys = [k for k in annot.AP.N.keys() if k != "/Off"]
                                    if keys:
                                        on_state = keys[0]
                                        
                                if is_truthy:
                                    from pdfrw import PdfName
                                    annot.V = PdfName(on_state.strip("/"))
                                    annot.AS = PdfName(on_state.strip("/"))
                                else:
                                    from pdfrw import PdfName
                                    annot.V = PdfName("Off")
                                    annot.AS = PdfName("Off")
                            else:
                                annot.V = f"{answer}"
                                annot.AP = None
                                
                            i += 1
                        else:
                            # Stop if we run out of answers
                            break

        PdfWriter().write(output_pdf, pdf)

        # Your main.py expects this function to return the path
        return output_pdf
