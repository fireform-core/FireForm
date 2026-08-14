"""Manual, end-to-end demo of the fill pipeline (not part of the package).

Run from the repo root with a real PDF path. This is a developer convenience
for exercising the services layer without the API; it is not imported anywhere.
"""

from commonforms import prepare_form
from pypdf import PdfReader

from app.services.controller import Controller

if __name__ == "__main__":
    file = "./data/inputs/file.pdf"  # update to a real input PDF
    user_input = (
        "Hi. The employee's name is John Doe. His job title is managing director. "
        "His department supervisor is Jane Doe. His phone number is 123456. "
        "His email is jdoe@ucsc.edu. The signature is <Mamanema>, and the date is 01/02/2005"
    )
    prepared_pdf = "temp_outfile.pdf"
    prepare_form(file, prepared_pdf)

    reader = PdfReader(prepared_pdf)
    fields = reader.get_fields()
    num_fields = len(fields) if fields else 0

    controller = Controller()
    controller.fill_form(user_input, fields, file)
