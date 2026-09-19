from datetime import datetime

from pdfrw import PdfName, PdfReader, PdfWriter

from app.services.llm import LLM


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values from the LLM.

        Fields are filled in visual order:
        top-to-bottom, left-to-right.

        Supports:
        - Text fields (/Tx)
        - Checkbox fields (/Btn)
        - Radio button fields (/Btn + radio flag)
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        # Generate answers from the LLM.
        t2j = llm.main_loop()
        textbox_answers = t2j.get_data()

        answers_list = list(textbox_answers.values())

        # Read PDF.
        pdf = PdfReader(pdf_form)

        # Fill fields in visual order.
        i = 0

        for page in pdf.pages:
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots,
                    key=lambda a: (
                        -float(a.Rect[1]),
                        float(a.Rect[0]),
                    ),
                )

                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        if i < len(answers_list):
                            answer = answers_list[i]

                            if annot.FT == "/Btn":
                                # PDF /Btn field can be a checkbox
                                # or a radio button.
                                field_flags = int(annot.Ff or 0)
                                is_radio = bool(field_flags & 32768)

                                if is_radio:
                                    # Radio button:
                                    # use the option supplied by the LLM.
                                    option = str(answer).strip().lstrip("/")

                                    annot.V = PdfName(option)
                                    annot.AS = PdfName(option)

                                elif answer:
                                    # Checkbox checked.
                                    annot.V = PdfName.Yes
                                    annot.AS = PdfName.Yes

                                else:
                                    # Checkbox unchecked.
                                    annot.V = PdfName.Off
                                    annot.AS = PdfName.Off

                            else:
                                # Preserve existing text-field behavior.
                                annot.V = f"{answer}"
                                annot.AP = None

                            i += 1

                        else:
                            # Stop if we run out of answers.
                            break

        PdfWriter().write(output_pdf, pdf)

        return output_pdf