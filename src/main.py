import os
from commonforms import prepare_form 
from pypdf import PdfReader
from controller import Controller

def input_fields(num_fields: int):
    """
    Helper function to manually input field definitions via CLI.
    """
    fields = []
    for i in range(num_fields):
        field = input(f"Enter description for field {i + 1}: ")
        fields.append(field)
    return fields

if __name__ == "__main__":
    file = "./src/inputs/file.pdf"
    user_input = "Hi. The employee's name is John Doe. His job title is managing director. His department supervisor is Jane Doe. His phone number is 123456. His email is jdoe@ucsc.edu. The signature is <Mamañema>, and the date is 01/02/2005"
    
    # Pre-defined fields (often overwritten by template fields)
    fields = ["Employee's name", "Employee's job title", "Employee's department supervisor", "Employee's phone number", "Employee's email", "Signature", "Date"]
    
    prepared_pdf = "temp_outfile.pdf"
    prepare_form(file, prepared_pdf)
    
    reader = PdfReader(prepared_pdf)
    template_fields = reader.get_fields()
    
    if template_fields:
        fields = template_fields
        num_fields = len(fields)
    else:
        num_fields = 0
        
    # fields = input_fields(num_fields) # Uncomment to manually edit fields
        
    controller = Controller()
    controller.fill_form(user_input, fields, file)
