import os

from app.core.logging import get_logger
from app.services.filler import Filler
from app.services.llm import LLM

logger = get_logger(__name__)


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def prepare_fillable(self, pdf_path: str):
        import os
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

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

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str, model: str = None, sign: bool = False):
        """
        It receives the raw data, runs the PDF filling logic,
        optionally signs it digitally, and returns the path to the newly created file.
        """
        logger.info("[1] Received request from frontend.")
        logger.info("[2] PDF template path: %s", pdf_form_path)

        if not os.path.exists(pdf_form_path):
            raise FileNotFoundError(f"PDF template not found at {pdf_form_path}")

        logger.info("[3] Starting extraction and PDF filling process...")
        try:
            self.llm._target_fields = fields
            self.llm._transcript_text = user_input
            self.llm._model = model
            output_name = self.filler.fill_form(pdf_form=pdf_form_path, llm=self.llm)

            # Metadata scrubbing (#315)
            try:
                from pdfrw import PdfReader, PdfWriter, PdfDict
                reader = PdfReader(output_name)
                reader.Info = PdfDict(
                    Title='FireForm Automated Report',
                    Author='FireForm',
                    Producer='FireForm',
                    Creator='FireForm'
                )
                PdfWriter().write(output_name, reader)
            except Exception as meta_err:
                logger.warning("Could not strip PDF metadata: %s", meta_err)

            # ISSUE #231: Digital Signature Integration 
            if sign:
                output_name = self._sign_pdf(output_name)

            logger.info("Process complete. Output saved to: %s", output_name)
            return output_name

        except Exception as e:
            logger.error("An error occurred during PDF generation: %s", e)
            raise e

    def _sign_pdf(self, pdf_path: str) -> str:
        """
        Sign the PDF using pyhanko if a certificate is configured.
        Falls back gracefully if no cert is found (preventing test breaks).
        """
        try:
            from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
            from pyhanko.sign import fields, signers

            cert_path = os.getenv("SIGNING_CERT_PATH", "cert.p12")
            cert_pass = os.getenv("SIGNING_CERT_PASSWORD", "").encode("utf-8")

            if not os.path.exists(cert_path):
                logger.warning("Signing requested, but certificate not found at %s. Skipping digital signature.", cert_path)
                return pdf_path

            with open(pdf_path, 'rb') as inf:
                w = IncrementalPdfFileWriter(inf)
                fields.append_signature_field(
                    w,
                    sig_field_spec=fields.SigFieldSpec(
                        sig_field_name='Sig1',
                        box=(50, 50, 200, 100)
                    )
                )

                signer = signers.load_pkcs12(
                    path=cert_path,
                    passphrase=cert_pass
                )

                output_signed_path = pdf_path.replace("_filled.pdf", "_signed.pdf")
                with open(output_signed_path, 'wb') as outf:
                    signers.sign_pdf(
                        w,
                        signers.PdfSignatureMetadata(field_name='Sig1'),
                        signer=signer,
                        output=outf
                    )

            os.replace(output_signed_path, pdf_path)
            logger.info("Successfully applied digital signature to PDF.")
        except Exception as e:
            logger.error("Failed to apply digital signature: %s", e)
        return pdf_path