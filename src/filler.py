from pdfrw import PdfReader, PdfWriter, PdfName
from src.llm import LLM
from datetime import datetime

class Filler:
    def __init__(self):
        pass

    def sort_annots_by_cluster(self, annots, y_tolerance=10.0):
        """
        Groups annotations into 'rows' based on their Y-coordinate (within a tolerance).
        Then sorts each row by the X-coordinate (left-to-right).
        """
        # First, roughly sort them top-to-bottom
        rough_sort = sorted(annots, key=lambda a: -float(a.Rect[1]))
        
        rows = []
        current_row = []
        current_y = None

        for annot in rough_sort:
            y_val = -float(annot.Rect[1])
            
            # If it's the first item, start the row
            if current_y is None:
                current_y = y_val
                current_row.append(annot)
                continue
            
            # If the current item is within the Y-tolerance of the current row
            if abs(y_val - current_y) <= y_tolerance:
                current_row.append(annot)
            else:
                # We've moved to a new row. Save the current one and start fresh.
                rows.append(current_row)
                current_row = [annot]
                current_y = y_val
                
        # Don't forget the last row
        if current_row:
            rows.append(current_row)

        # Now, sort each row left-to-right (by X coordinate)
        final_sorted = []
        for row in rows:
            sorted_row = sorted(row, key=lambda a: float(a.Rect[0]))
            final_sorted.extend(sorted_row)

        return final_sorted


    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values from user_input using LLM.
        Fields are filled in visual order using clustered spatial sorting.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        # Generate dictionary of answers
        t2j = llm.main_loop()
        textbox_answers = t2j.get_data() 

        answers_list = list(textbox_answers.values())

        # Read PDF
        pdf = PdfReader(pdf_form)

        # Loop through pages
        for page in pdf.pages:
            if page.Annots:
                # -- NEW CLUSTER SORTING LOGIC --
                sorted_annots = self.sort_annots_by_cluster(page.Annots)

                i = 0
                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        if i < len(answers_list):
                            val = str(answers_list[i])
                            
                            # CHECKBOX LOGIC (From previous PR)
                            if annot.FT == "/Btn":
                                if val.lower() in ["yes", "on", "true"]:
                                    annot.V = PdfName("Yes") 
                                    annot.AS = PdfName("Yes")
                                else:
                                    annot.V = PdfName("Off")
                                    annot.AS = PdfName("Off")
                            
                            # STANDARD TEXT LOGIC
                            else:
                                annot.V = f"{val}"
                                annot.AP = None 
                            
                            i += 1
                        else:
                            break

        PdfWriter().write(output_pdf, pdf)

        return output_pdf