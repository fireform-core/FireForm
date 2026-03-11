import os
from typing import Union
from commonforms import prepare_form 
from pypdf import PdfReader
from controller import Controller
from logger import setup_logger

logger = setup_logger(__name__)

def input_fields(num_fields: int):
    fields = []
    for i in range(num_fields):
        field = input(f"Enter description for field {i + 1}: ")
        fields.append(field)
    return fields

def run_pdf_fill_process(user_input: str, definitions: Union[dict, list], pdf_form_path: Union[str, os.PathLike]):
    """
    This function is called by the frontend server.
    It receives the raw data, runs the PDF filling logic,
    and returns the path to the newly created file.
    """
    
    logger.info("Received request from frontend.")
    logger.info("PDF template path: %s", pdf_form_path)
    
    # Normalize Path/PathLike to a plain string for downstream code
    pdf_form_path = os.fspath(pdf_form_path)
    
    if not os.path.exists(pdf_form_path):
        logger.error("PDF template not found at %s", pdf_form_path)
        return None # Or raise an exception

    logger.info("Starting extraction and PDF filling process...")
    try:
        controller = Controller()
        output_name = controller.fill_form(
            user_input=user_input,
            fields=definitions,
            pdf_form_path=pdf_form_path
        )
        
        logger.info("Process complete. Output saved to: %s", output_name)
        
        return output_name
        
    except Exception as e:
        logger.exception("An error occurred during PDF generation: %s", e)
        # Re-raise the exception so the frontend can handle it
        raise e


# if __name__ == "__main__":
#     file = "./src/inputs/file.pdf"
#     user_input = "Hi. The employee's name is John Doe. His job title is managing director. His department supervisor is Jane Doe. His phone number is 123456. His email is jdoe@ucsc.edu. The signature is <Mamañema>, and the date is 01/02/2005"
#     fields = ["Employee's name", "Employee's job title", "Employee's department supervisor", "Employee's phone number", "Employee's email", "Signature", "Date"]
#     prepared_pdf = "temp_outfile.pdf"
#     prepare_form(file, prepared_pdf)
    
#     reader = PdfReader(prepared_pdf)
#     fields = reader.get_fields()
#     if(fields):
#         num_fields = len(fields)
#     else:
#         num_fields = 0
#     #fields = input_fields(num_fields) # Uncomment to edit fields
    
#     run_pdf_fill_process(user_input, fields, file)

if __name__ == "__main__":
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
