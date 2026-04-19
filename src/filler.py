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
                            # Stop if we run out of answers
                            break

        PdfWriter().write(output_pdf, pdf)

        # --- Verification Step ---
        import logging
        logger = logging.getLogger(__name__)
        logger.info("\t[LOG]: Starting PDF fill verification...")
        
        filled_pdf = PdfReader(output_pdf)
        written_answers = []
        for page in filled_pdf.pages:
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )
                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        val = str(annot.V) if annot.V else ""
                        if val.startswith("(") and val.endswith(")"):
                            val = val[1:-1]
                        written_answers.append(val)
        
        mismatches = 0
        correct = 0
        missing = 0
        for i in range(len(answers_list)):
            expected = str(answers_list[i])
            if i < len(written_answers):
                actual = written_answers[i]
                if actual != expected:
                    logger.warning(f"  [!] Mismatch at field index {i}: Expected '{expected}', Found '{actual}'")
                    mismatches += 1
                else:
                    correct += 1
            else:
                logger.warning(f"  [?] Missing field at index {i}: Expected '{expected}', Found nothing")
                missing += 1
                
        logger.info(f"\t[LOG]: Verification Summary: ✔ Correct {correct} | ✖ Mismatch {mismatches} | ⚠ Missing {missing}")

        # Your main.py expects this function to return the path
        return output_pdf
