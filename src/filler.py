from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from src.compatibility_checker import CompatibilityChecker
from src.template_schema import TemplateRegistry
from datetime import datetime
from typing import Optional


class Filler:
    def __init__(
        self,
        template_registry: Optional[TemplateRegistry] = None,
    ):
        self.template_registry = template_registry
        self.compatibility_checker = (
            CompatibilityChecker(template_registry)
            if template_registry
            else None
        )

    def check_compatibility_before_fill(
        self,
        template_id: str,
        extracted_data: dict,
    ) -> dict:
        """Check if extracted data is compatible with a template before filling.
        
        Args:
            template_id: ID of the template to check against.
            extracted_data: Extracted field data to validate.
            
        Returns:
            Compatibility report dict with status and details.
            
        Raises:
            ValueError: If no template registry is configured or template not found.
        """
        if not self.compatibility_checker:
            raise ValueError("Template registry not configured in Filler instance")
        
        report = self.compatibility_checker.check_compatibility(
            template_id,
            extracted_data,
        )
        
        return {
            "compatible": report.compatible,
            "missing_fields": sorted(report.missing_fields),
            "extra_fields": sorted(report.extra_fields),
            "unmapped_fields": sorted(report.unmapped_fields),
            "type_mismatches": report.type_mismatches,
            "dependency_violations": report.dependency_violations,
            "warnings": report.warnings,
            "matched_fields": sorted(report.matched_fields),
            "summary": report.summary(),
        }

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

        # Your main.py expects this function to return the path
        return output_pdf
