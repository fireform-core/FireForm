import logging
import os

from commonforms import prepare_form

from src.filler import Filler
from src.llm import LLM
from src.template_mapper import TemplateMapper

logger = logging.getLogger(__name__)


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def create_template(self, pdf_path: str) -> str:
        """
        Prepare a fillable PDF template using commonforms and return its path.
        """
        template_path = pdf_path[:-4] + "_template.pdf"
        prepare_form(pdf_path, template_path)
        return template_path

    def fill_form(
        self,
        user_input: str,
        fields: dict,
        pdf_form_path: str,
        yaml_path: str | None = None,
    ) -> str:
        """
        Extract data from user_input and fill pdf_form_path.

        When yaml_path is provided and the file exists, the new pipeline is used:
          LLM → IncidentReport → TemplateMapper → Filler (named fields)

        When yaml_path is absent, falls back to the legacy pipeline:
          LLM → raw dict → Filler (positional fields)

        Returns the path to the filled PDF.
        """
        logger.info("Received fill request. PDF: %s  YAML: %s", pdf_form_path, yaml_path)

        if not os.path.exists(pdf_form_path):
            raise FileNotFoundError(f"PDF template not found at {pdf_form_path}")

        self.llm._transcript_text = user_input

        if yaml_path and os.path.exists(yaml_path):
            return self._fill_with_mapper(yaml_path)

        logger.warning(
            "No YAML template provided or found at %r — using legacy positional mapping.",
            yaml_path,
        )
        return self._fill_legacy(fields, pdf_form_path)

    # -------------------------------------------------------------------------
    # New pipeline: LLM → IncidentReport → TemplateMapper → Filler
    # -------------------------------------------------------------------------

    def _fill_with_mapper(self, yaml_path: str) -> str:
        mapper = TemplateMapper(yaml_path)

        self.llm.main_loop()
        report = self.llm.get_report()

        if report and report.requires_review:
            logger.warning(
                "Extraction incomplete — the following fields require manual review: %s",
                report.requires_review,
            )

        field_values = mapper.resolve(report)
        return self.filler.fill_form(pdf_form=mapper.pdf_path, field_values=field_values)

    # -------------------------------------------------------------------------
    # Legacy pipeline: kept for backward compatibility until all templates have
    # YAML mappings (Phase 2, Week 5).
    # -------------------------------------------------------------------------

    def _fill_legacy(self, fields: dict, pdf_form_path: str) -> str:
        self.llm._target_fields = fields
        self.llm.main_loop()
        data = self.llm.get_data()

        # Build a positional {field_name: value} dict from the PDF's own field names
        # and the extracted values in visual order — brittle, but preserved until
        # YAML templates cover all forms.
        from pdfrw import PdfReader

        pdf = PdfReader(pdf_form_path)
        pdf_fields = []
        for page in pdf.pages:
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )
                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        pdf_fields.append(self.filler._field_name(annot.T))

        values = [v for v in data.values() if v is not None]
        field_values = {
            pdf_fields[i]: str(values[i])
            for i in range(min(len(pdf_fields), len(values)))
        }

        return self.filler.fill_form(pdf_form=pdf_form_path, field_values=field_values)
