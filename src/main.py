import os
import logging
from typing import Union
from pypdf import PdfReader
from .controller import Controller

# Set up logger
logger = logging.getLogger(__name__)

def input_fields(num_fields: int):
    fields = []
    for i in range(num_fields):
        field = input(f"Enter description for field {i + 1}: ")
        fields.append(field)
    return fields

def run_pdf_fill_process(user_input: str, definitions: list, pdf_form_path: Union[str, os.PathLike]):
    """
    This function is called by the frontend server.
    It receives the raw data, runs the PDF filling logic,
    and returns the path to the newly created file and review flag.
    
    Returns:
        tuple: (output_path, requires_review_flag)
    """
    
    logger.info("Received request from frontend")
    logger.info(f"PDF template path: {pdf_form_path}")
    
    # Normalize Path/PathLike to a plain string for downstream code
    pdf_form_path = os.fspath(pdf_form_path)
    
    if not os.path.exists(pdf_form_path):
        logger.error(f"PDF template not found at {pdf_form_path}")
        raise FileNotFoundError(f"PDF template not found at {pdf_form_path}")

    logger.info("Starting extraction and PDF filling process")
    try:
        controller = Controller()
        output_name, requires_review = controller.fill_form(
            user_input=user_input,
            fields=definitions,
            pdf_form_path=pdf_form_path
        )
        
        logger.info("Process complete")
        logger.info(f"Output saved to: {output_name}")
        logger.info(f"Requires review: {requires_review}")
        
        return output_name, requires_review
        
    except (ValueError, RuntimeError, OSError, FileNotFoundError) as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise ValueError("PDF generation failed") from e
    except Exception as e:
        logger.error(f"Unexpected error during PDF generation: {e}", exc_info=True)
        raise RuntimeError("PDF generation failed") from e


if __name__ == "__main__":
    from commonforms import prepare_form
    
    # Example usage
    file = "./src/inputs/file.pdf"
    user_input = "Hi. The employee's name is John Doe. His job title is managing director. His department supervisor is Jane Doe. His phone number is 123456. His email is jdoe@ucsc.edu. The signature is <Mamañema>, and the date is 01/02/2005"
    fields = ["Employee's name", "Employee's job title", "Employee's department supervisor", "Employee's phone number", "Employee's email", "Signature", "Date"]
    prepared_pdf = "temp_outfile.pdf"
    
    try:
        prepare_form(file, prepared_pdf)
        
        reader = PdfReader(prepared_pdf)
        pdf_fields = reader.get_fields()
        if pdf_fields:
            num_fields = len(pdf_fields)
            logger.info(f"Found {num_fields} fields in PDF")
        else:
            num_fields = 0
            logger.warning("No fields found in PDF")
            
        controller = Controller()
        output_path, requires_review = controller.fill_form(user_input, fields, file)
        
        print(f"\n✅ Process Complete")
        print(f"Output: {output_path}")
        print(f"Requires Review: {requires_review}")
        
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        print(f"❌ Error: {e}")
