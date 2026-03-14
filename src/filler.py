from pdfrw import PdfReader, PdfWriter, PdfName
from src.llm import LLM
from datetime import datetime


# Values the LLM might return meaning "yes/checked"
TRUTHY_VALUES = {"yes", "true", "1", "on", "checked", "x", "selected"}

# Values the LLM might return meaning "no/unchecked"
FALSY_VALUES = {"no", "false", "0", "off", "unchecked", "", "none", "null"}


def _resolve_checkbox_value(raw_value: str, annot) -> str:
    """
    Convert LLM string output to correct PDF checkbox value.

    PDF checkboxes use named values like /Yes and /Off — not strings.
    The exact "on" value varies per PDF (commonly /Yes but can be /On, /True etc).
    We read the annotation's own AP dictionary to find what it expects.

    Returns the correct PdfName value to write.
    """
    normalized = str(raw_value).strip().lower()

    # Determine intent from LLM output
    is_checked = normalized in TRUTHY_VALUES

    if is_checked:
        # Try to read the PDF's own "on" state name from appearance stream
        # AP.N contains normal appearance states — keys are the valid values
        try:
            if annot.AP and annot.AP.N:
                for key in annot.AP.N.keys():
                    clean = str(key).strip("/")
                    if clean.lower() not in ("off", "false", "0"):
                        return PdfName(clean)  # e.g. PdfName("Yes")
        except Exception:
            pass
        return PdfName("Yes")  # safe universal fallback
    else:
        return PdfName("Off")


def _resolve_radio_value(raw_value: str, annot) -> str:
    """
    Convert LLM string output to correct PDF radio button value.

    Radio buttons work like checkboxes but the "on" value is the
    option label (e.g. /Male, /Option1). We read it from AP.N.
    """
    normalized = str(raw_value).strip().lower()
    is_selected = normalized in TRUTHY_VALUES

    if is_selected:
        try:
            if annot.AP and annot.AP.N:
                for key in annot.AP.N.keys():
                    clean = str(key).strip("/")
                    if clean.lower() not in ("off", "false", "0"):
                        return PdfName(clean)
        except Exception:
            pass
        return PdfName("Yes")
    else:
        return PdfName("Off")


def _get_field_type(annot) -> str:
    """
    Return the PDF field type: 'text', 'checkbox', 'radio', or 'other'.
    FT /Btn = button (checkbox or radio).
    FT /Tx  = text field.
    """
    ft = str(annot.FT).strip("/") if annot.FT else ""
    if ft == "Btn":
        # Ff (field flags) bit 16 = radio button
        try:
            ff = int(str(annot.Ff)) if annot.Ff else 0
            if ff & (1 << 15):  # bit 16 (0-indexed as 15)
                return "radio"
        except Exception:
            pass
        return "checkbox"
    elif ft == "Tx":
        return "text"
    return "other"


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values from user_input using LLM.
        Fields are filled in the visual order (top-to-bottom, left-to-right).
        Supports text fields, checkboxes, and radio buttons.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        t2j = llm.main_loop()
        textbox_answers = t2j.get_data()
        answers_list = list(textbox_answers.values())

        pdf = PdfReader(pdf_form)

        for page in pdf.pages:
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )

                i = 0
                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        if i < len(answers_list):
                            raw = answers_list[i]
                            field_type = _get_field_type(annot)

                            if field_type == "checkbox":
                                annot.V = _resolve_checkbox_value(raw, annot)
                                annot.AS = annot.V  # AS must match V for rendering
                            elif field_type == "radio":
                                annot.V = _resolve_radio_value(raw, annot)
                                annot.AS = annot.V
                            else:
                                # Plain text field — write as string, never "None"
                                annot.V = "" if raw is None else str(raw)

                            annot.AP = None
                            i += 1
                        else:
                            break

        PdfWriter().write(output_pdf, pdf)
        return output_pdf

    def fill_form_with_data(self, pdf_form: str, data: dict) -> str:
        """
        Fill a PDF form with a pre-extracted data dictionary.
        Used by batch endpoint — NO LLM call made here.
        Matches fields by their exact PDF annotation key (T field).
        Supports text fields, checkboxes, and radio buttons.

        This is the deterministic filling path:
          extracted_json → subset per template → fill PDF
        No hallucination risk — pure Python key matching.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        pdf = PdfReader(pdf_form)

        for page in pdf.pages:
            if page.Annots:
                for annot in page.Annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        field_key = annot.T.strip("()")
                        if field_key in data and data[field_key] is not None:
                            raw = data[field_key]
                            field_type = _get_field_type(annot)

                            if field_type == "checkbox":
                                annot.V = _resolve_checkbox_value(raw, annot)
                                annot.AS = annot.V
                            elif field_type == "radio":
                                annot.V = _resolve_radio_value(raw, annot)
                                annot.AS = annot.V
                            else:
                                # Plain text — never write literal "None"
                                annot.V = "" if raw is None else str(raw)

                            annot.AP = None

        PdfWriter().write(output_pdf, pdf)
        return output_pdf