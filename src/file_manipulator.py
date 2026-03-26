import os
from src.filler import Filler
from src.llm import LLM
from commonforms import prepare_form
import logging
from pathlib import Path

# Only configure logging if not already configured
logger = logging.getLogger(__name__)
if not logger.handlers:
    # Configure logging only once
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def create_template(self, pdf_path: str):
        """
        By using commonforms, we create an editable .pdf template and we store it.
        """
        template_path = Path(pdf_path).parent / f"{Path(pdf_path).stem}_template.pdf"
        prepare_form(pdf_path, template_path)
        return str(template_path)

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
        """
        It receives the raw data, runs the PDF filling logic,
        and returns the path to the newly created file and a review flag.
        """
        # Input validation
        if user_input is None:
            raise ValueError("User input cannot be None")
        if fields is None:
            raise ValueError("Fields cannot be None")
        if pdf_form_path is None:
            raise ValueError("PDF form path cannot be None")
        
        if not isinstance(user_input, str):
            raise TypeError("User input must be a string")
        if not isinstance(fields, (list, dict)):
            raise TypeError("Fields must be a list or dictionary")
        if not isinstance(pdf_form_path, str):
            raise TypeError("PDF form path must be a string")
        
        if not user_input.strip():
            raise ValueError("User input cannot be empty")
        if not fields:
            raise ValueError("Fields cannot be empty")
        if not pdf_form_path.strip():
            raise ValueError("PDF form path cannot be empty")
        
        # Path traversal validation
        import re
        path_traversal_pattern = re.compile(r'(?:\.\.[\\/]|\.\.%2[fF]|\.\.%5[cC])')
        if path_traversal_pattern.search(pdf_form_path):
            raise ValueError("Path traversal detected in PDF path")
        
        # Normalize path and check it's within allowed directory
        from pathlib import Path
        try:
            pdf_path_obj = Path(pdf_form_path).resolve()
        except (ValueError, OSError) as e:
            raise ValueError(f"Invalid PDF path: {e}")
        
        # Check if file exists
        if not pdf_path_obj.exists():
            logger.error(f"PDF template not found at {pdf_form_path}")
            raise FileNotFoundError(f"PDF template not found at {pdf_form_path}")
        
        # Check it's a file, not a directory
        if not pdf_path_obj.is_file():
            raise ValueError("PDF path must be a file, not a directory")

        logger.info("Received request from frontend")
        logger.info(f"PDF template path: {pdf_form_path}")

        # Check PDF file extension
        if not pdf_form_path.lower().endswith('.pdf'):
            raise ValueError("File must be a PDF")

        logger.info("Starting extraction and PDF filling process")
        try:
            # Check file size (prevent memory exhaustion)
            file_size = os.path.getsize(pdf_form_path)
            if file_size > 100 * 1024 * 1024:  # 100MB limit
                raise ValueError("PDF file too large (max 100MB)")
            
            # Check file permissions
            if not os.access(pdf_form_path, os.R_OK):
                raise PermissionError("Cannot read PDF file")
            
            # Use existing LLM instance with updated parameters
            self.llm._transcript_text = user_input
            self.llm._target_fields = fields
            
            # Try structured extraction first, fallback to old method
            logger.info("Attempting structured extraction...")
            extraction_success = False
            
            try:
                extraction_success = self.llm.extract_structured_safe()
            except Exception as e:
                logger.warning(f"Structured extraction raised exception: {e}", exc_info=True)
                extraction_success = False
            
            if not extraction_success:
                logger.info("Structured extraction failed, falling back to field-by-field extraction")
                try:
                    self.llm.main_loop()
                except Exception as e:
                    logger.error(f"Field-by-field extraction also failed: {e}", exc_info=True)
                    raise RuntimeError("Both extraction methods failed") from e
            
            # Verify we have extracted data
            extracted_data = self.llm.get_data()
            if not extracted_data or not isinstance(extracted_data, dict):
                raise ValueError("No data extracted from input")
            
            # Fill the PDF
            try:
                output_name = self.filler.fill_form(pdf_form=pdf_form_path, llm=self.llm)
            except Exception as e:
                logger.error(f"PDF filling failed: {e}", exc_info=True)
                raise RuntimeError("PDF filling failed") from e
            
            if not output_name or not isinstance(output_name, str):
                raise ValueError("PDF filling returned invalid output path")
            
            # Check if manual review is needed
            try:
                from src.utils.validation import requires_review
                
                # Get field keys
                if isinstance(fields, list):
                    field_keys = fields
                elif isinstance(fields, dict):
                    field_keys = list(fields.keys())
                else:
                    field_keys = []
                
                review_flag = requires_review(extracted_data, field_keys)
            except Exception as e:
                logger.warning(f"Review check failed: {e}", exc_info=True)
                # Default to requiring review if check fails
                review_flag = True

            logger.info("Process completed successfully")
            logger.info(f"Output saved to: {output_name}")
            logger.info(f"Requires review: {review_flag}")

            return output_name, review_flag

        except (ValueError, RuntimeError, OSError, PermissionError) as e:
            logger.error(f"PDF generation failed: {e}", exc_info=True)
            raise ValueError("PDF generation failed") from e
        except Exception as e:
            logger.error(f"Unexpected error during PDF generation: {e}", exc_info=True)
            raise RuntimeError("PDF generation failed") from e
