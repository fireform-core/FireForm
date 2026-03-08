from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM, map_image_path: str = None):
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
        # Note: LLM has already run its main_loop upstream in file_manipulator before calling this.
        textbox_answers = llm.get_data()  # This is a dictionary
        
        # Remove "Location Summary" from the answers so we don't accidentally fill it into a standard visual field
        if "Location Summary" in textbox_answers:
            del textbox_answers["Location Summary"]

        answers_list = list(textbox_answers.values())

        # Read PDF via pdfrw
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
        
        # Step 2: Overlay map image onto the PDF if generation was successful
        if map_image_path and os.path.exists(map_image_path):
            import fitz
            doc = fitz.open(output_pdf)
            # Insert on the first page
            page = doc[0]
            # Define where the map image goes: bottom right corner, width 150, height 100
            rect = fitz.Rect(page.rect.width - 200, page.rect.height - 150, page.rect.width - 50, page.rect.height - 50)
            page.insert_image(rect, filename=map_image_path)
            doc.saveIncr()
            doc.close()
            # Clean up temporary map image
            try:
                os.remove(map_image_path)
            except OSError:
                pass

        # Your main.py expects this function to return the path
        return output_pdf
