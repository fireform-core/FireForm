from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from src.audit import AuditMetadata
from datetime import datetime
from typing import Optional


class Filler:
    def __init__(self):
        self.audit = AuditMetadata()

    def fill_form(
        self,
        pdf_form: str,
        llm: LLM,
        gps_latitude: Optional[float] = None,
        gps_longitude: Optional[float] = None,
        device_id: Optional[str] = None,
        officer_name: Optional[str] = None,
    ):
        """
        Fill a PDF form with values from user_input using LLM.
        Fields are filled in the visual order (top-to-bottom, left-to-right).
        
        Args:
            pdf_form: Path to the PDF form template
            llm: LLM instance for text extraction and processing
            gps_latitude: GPS latitude coordinate
            gps_longitude: GPS longitude coordinate
            device_id: Unique device identifier
            officer_name: Name of the officer generating the PDF
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        # Set audit metadata with generation timestamp
        timestamp = datetime.utcnow().isoformat()
        self.audit.set_metadata(
            timestamp=timestamp,
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            device_id=device_id,
            officer_name=officer_name,
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

        # Save audit metadata to JSON file
        audit_json_path = self.audit.save_to_json(output_pdf)
        print(f"📋 Audit metadata saved to: {audit_json_path}")

        # Your main.py expects this function to return the path
        return output_pdf
