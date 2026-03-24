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
    and returns the path to the newly created file.
    """
    
    print("[1] Received request from frontend.")
    print(f"[2] PDF template path: {pdf_form_path}")
    
    # Normalize Path/PathLike to a plain string for downstream code
    pdf_form_path = os.fspath(pdf_form_path)
    
    if not os.path.exists(pdf_form_path):
        print(f"Error: PDF template not found at {pdf_form_path}")
        return None # Or raise an exception

    print("[3] Starting extraction and PDF filling process...")
    try:
        controller = Controller()
        output_name = controller.fill_form(
            user_input=user_input,
            fields=definitions,
            pdf_form_path=pdf_form_path
        )
        
        print("\n----------------------------------")
        print(f"✅ Process Complete.")
        print(f"Output saved to: {output_name}")
        
        return output_name
        
    except (ValueError, RuntimeError, OSError) as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        print("An error occurred during PDF generation")
        # Re-raise the exception so the frontend can handle it
        raise ValueError("PDF generation failed") from e
    except Exception as e:
        logger.error(f"Unexpected error during PDF generation: {e}", exc_info=True)
        print("An unexpected error occurred during PDF generation")
        raise RuntimeError("PDF generation failed") from e


if __name__ == "__main__":
    from commonforms import prepare_form
    
    file = "./src/inputs/file.pdf"
    user_input = "Hi. The employee's name is John Doe. His job title is managing director. His department supervisor is Jane Doe. His phone number is 123456. His email is jdoe@ucsc.edu. The signature is <Mamañema>, and the date is 01/02/2005"
    fields = ["Employee's name", "Employee's job title", "Employee's department supervisor", "Employee's phone number", "Employee's email", "Signature", "Date"]
    prepared_pdf = "temp_outfile.pdf"
    prepare_form(file, prepared_pdf)
    
    reader = PdfReader(prepared_pdf)
    fields = reader.get_fields()
    if(fields):
        num_fields = len(fields)
    else:
        num_fields = 0
        
    controller = Controller()
    controller.fill_form(user_input, fields, file)
