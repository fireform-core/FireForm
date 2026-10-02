import os
from datetime import datetime

from pdfrw import PdfDict, PdfReader, PdfWriter

from app.core.logging import get_logger
from app.services.form_filler import filler

logger = get_logger(__name__)


class FileManipulator:

    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def prepare_fillable(self, pdf_path: str):
        """
        Run commonforms on a flat PDF to detect form regions and produce a
        fillable PDF. Returns the new path (alongside the original).
        """
        # Disable CUDA to force CPU usage, preventing errors on
        # Mac Silicon / Docker
        import os
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

        # Monkey patch rfdetr to force CPU usage on Mac Silicon / Docker
        try:
            import rfdetr.detr
            original_ensure = rfdetr.detr._ensure_model_on_device

            def patched_ensure(model_ctx):
                model_ctx.device = "cpu"
                original_ensure(model_ctx)

            rfdetr.detr._ensure_model_on_device = patched_ensure
        except ImportError:
            pass

        from commonforms import prepare_form
        template_path = pdf_path[:-4] + "_template.pdf"

        prepare_form(pdf_path, template_path)
        return template_path

    def fill_form(
        self,
        user_input: str,
        fields: list,
        pdf_form_path: str,
        model: str = None,
    ):
        """
        It receives the raw data, runs the PDF filling logic,
        and returns the path to the newly created file.

        `fields` is unused: form_filler reads the fields, tables and tooltip
        descriptions straight from the PDF.
        """
        logger.info("[1] Received request from frontend.")
        logger.info("[2] PDF template path: %s", pdf_form_path)

        if not os.path.exists(pdf_form_path):
            raise FileNotFoundError(
                f"PDF template not found at {pdf_form_path}"
            )

        logger.info("[3] Starting extraction and PDF filling process...")
        try:
            self.llm._target_fields = fields
            self.llm._transcript_text = user_input
            self.llm._model = model
            output_name = self.filler.fill_form(
                pdf_form=pdf_form_path, llm=self.llm
            )

            # ISSUE #315: Metadata Scrubbing Pipeline
            try:
                reader = PdfReader(output_name)
                # Reinitialize the Info dictionary with an
                # anonymous/standardized profile
                reader.Info = PdfDict(
                    Title="FireForm Automated Report",
                    Author="FireForm",
                    Producer="FireForm",
                    Creator="FireForm",
                )
                PdfWriter().write(output_name, reader)
                logger.info(
                    "Successfully scrubbed sensitive metadata from output PDF."
                )
            except Exception as meta_err:
                logger.warning(
                    "Could not strip PDF metadata: %s", meta_err
                )
            # ===============================================

            logger.info(
                "Process complete. Output saved to: %s", output_name
            )

            return output_name

        except Exception as e:
            logger.error(
                "An error occurred during PDF generation: %s", e
            )
            raise e