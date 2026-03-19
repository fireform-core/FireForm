from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime
import os

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

        answers_list = []
        for data in textbox_answers.values():
            if isinstance(data, dict):
                answers_list.append(data.get("value", ""))
            elif isinstance(data, list) and len(data) > 0:
                answers_list.append(data[0].get("value", ""))
            else:
                answers_list.append(str(data))

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

        # --- ZERO-DEPENDENCY AUDIT TRAIL ---
        # Create a text file with the same name as the PDF
        audit_txt_path = output_pdf.replace(".pdf", "_audit.txt")
        
        with open(audit_txt_path, "w", encoding="utf-8") as f:
            f.write("="*60 + "\n")
            f.write("FIREFORM AI DATA EXTRACTION AUDIT TRAIL\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*60 + "\n\n")
            
            for field, data in textbox_answers.items():
                # Parse out the value and quote safely
                if isinstance(data, dict):
                    val = data.get("value", "N/A")
                    quote = data.get("quote", "N/A")
                elif isinstance(data, list) and len(data) > 0:
                    val = data[0].get("value", "N/A")
                    quote = data[0].get("quote", "N/A")
                else:
                    val, quote = str(data), "N/A"
                
                f.write(f"FIELD : {field}\n")
                f.write(f"VALUE : {val}\n")
                f.write(f"SOURCE: \"{quote}\"\n")
                f.write("-" * 60 + "\n")
                
        print(f"\t[LOG] Audit trail saved to: {audit_txt_path}")
        # -----------------------------------

        # Your main.py expects this function to return the path
        return output_pdf