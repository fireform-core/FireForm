import os

from app.core.logging import get_logger
from app.services.filler import Filler
from app.services.form_fill import extract_field_values

logger = get_logger(__name__)


class FileManipulator:
    def __init__(self):
        self.filler = Filler()

    def prepare_fillable(self, pdf_path: str):
        """
        Run commonforms on a flat PDF to detect form regions and produce a
        fillable PDF. Returns the new path (alongside the original).
        """
        # Disable CUDA to force CPU usage, preventing errors on Mac Silicon / Docker
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

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str, model: str = None):
        """
        It receives the raw data, runs the PDF filling logic,
        and returns the path to the newly created file.
        """
        logger.info("[1] Received request from frontend.")
        logger.info("[2] PDF template path: %s", pdf_form_path)

        if not os.path.exists(pdf_form_path):
            raise FileNotFoundError(f"PDF template not found at {pdf_form_path}")

        logger.info("[3] Starting extraction and PDF filling process...")
        try:
            values = extract_field_values(user_input, fields, model=model)
            output_name = self.filler.fill_form(pdf_form_path, values)

            logger.info("Process complete. Output saved to: %s", output_name)

            return output_name

        except Exception as e:
            logger.error("An error occurred during PDF generation: %s", e)
            raise e
