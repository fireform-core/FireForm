from pdfrw import PdfReader, PdfWriter, PdfName
from src.llm import LLM
from datetime import datetime


TRUTHY_VALUES = {"yes", "true", "1", "on", "checked", "x", "selected", "male", "female"}
FALSY_VALUES  = {"no", "false", "0", "off", "unchecked", "", "none", "null"}


def _resolve_checkbox_value(raw_value, annot):
    """
    Convert LLM string → correct PDF checkbox value (/Yes or /Off).
    Reads the PDF's own AP.N keys to find the exact 'on' state name.
    """
    normalized = str(raw_value).strip().lower()
    is_checked = normalized in TRUTHY_VALUES

    if is_checked:
        try:
            if annot.AP and annot.AP.N:
                for key in annot.AP.N.keys():
                    clean = str(key).strip("/")
                    if clean.lower() not in ("off", "false", "0", "length",
                                             "subtype", "bbox", "resources"):
                        return PdfName(clean)
        except Exception:
            pass
        return PdfName("Yes")
    return PdfName("Off")


def _resolve_radio_kid(raw_value, kid_index, annot):
    """
    For a radio button kid annotation, determine if THIS kid should be selected.
    raw_value is the LLM output (e.g. "female").
    kid_index is 0 for Male, 1 for Female etc.

    Reads /Opt from the parent to match the intended option.
    Returns the 'on' PdfName if selected, /Off otherwise.
    """
    normalized = str(raw_value).strip().lower()

    # Try to match against /Opt list on parent
    try:
        parent = annot.Parent
        if parent and parent.Opt:
            opts = [str(o).strip("()").lower() for o in parent.Opt]
            if kid_index < len(opts):
                if opts[kid_index] == normalized:
                    # This kid is the selected one — find its 'on' value
                    if annot.AP and annot.AP.N:
                        for key in annot.AP.N.keys():
                            clean = str(key).strip("/")
                            if clean.lower() not in ("off", "false", "0"):
                                return PdfName(clean)
                    return PdfName(str(kid_index))
    except Exception:
        pass

    return PdfName("Off")


def _get_field_type(annot):
    """Return 'text', 'checkbox', 'radio', 'dropdown', or 'other'."""
    ft = str(annot.FT).strip("/") if annot.FT else ""
    if ft == "Btn":
        try:
            ff = int(str(annot.Ff)) if annot.Ff else 0
            if ff & (1 << 15):
                return "radio"
            if ff & (1 << 16):
                return "pushbutton"
        except Exception:
            pass
        return "checkbox"
    elif ft == "Tx":
        return "text"
    elif ft == "Ch":
        return "dropdown"
    return "other"


def _fill_annotation(annot, raw_value):
    """
    Write the correct value to a single annotation based on its field type.
    Handles text, checkbox, and radio buttons.
    """
    field_type = _get_field_type(annot)

    if field_type == "checkbox":
        annot.V  = _resolve_checkbox_value(raw_value, annot)
        annot.AS = annot.V

    elif field_type == "radio":
        # Parent radio group — set V on parent, AS on each kid
        if annot.Kids:
            normalized = str(raw_value).strip().lower()
            # Find which option matches
            selected_index = None
            try:
                opts = [str(o).strip("()").lower() for o in annot.Opt]
                if normalized in opts:
                    selected_index = opts.index(normalized)
            except Exception:
                pass

            for i, kid in enumerate(annot.Kids):
                if selected_index is not None and i == selected_index:
                    # Find the kid's 'on' AP key
                    on_val = PdfName(str(i))
                    try:
                        if kid.AP and kid.AP.N:
                            for key in kid.AP.N.keys():
                                clean = str(key).strip("/")
                                if clean.lower() not in ("off", "false", "0"):
                                    on_val = PdfName(clean)
                                    break
                    except Exception:
                        pass
                    kid.AS = on_val
                    annot.V = on_val
                else:
                    kid.AS = PdfName("Off")
        else:
            # Leaf radio kid — handled via parent traversal
            annot.V  = _resolve_checkbox_value(raw_value, annot)
            annot.AS = annot.V

    elif field_type == "pushbutton":
        pass  # Skip — reset/submit buttons, never fill

    elif field_type == "dropdown":
        # Write as-is — pdfrw handles /Ch display
        annot.V = "" if raw_value is None else str(raw_value)

    else:
        # Plain text — never write literal "None"
        annot.V = "" if raw_value is None else str(raw_value)

    annot.AP = None


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values from user_input using LLM.
        Supports text, checkbox, radio buttons, and dropdowns.
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
                    if annot.Subtype == "/Widget":
                        if annot.T and i < len(answers_list):
                            _fill_annotation(annot, answers_list[i])
                            annot.AP = None
                            i += 1
                        elif not annot.T and annot.Parent:
                            # Kid annotation — skip, handled by parent
                            pass

        PdfWriter().write(output_pdf, pdf)
        return output_pdf

    def fill_form_with_data(self, pdf_form: str, data: dict) -> str:
        """
        Fill a PDF form with a pre-extracted data dictionary.
        Used by batch endpoint — NO LLM call made here.
        Matches fields by annotation key (T field) or parent T field.
        Supports text, checkbox, radio buttons, and dropdowns.
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
                    if annot.Subtype != "/Widget":
                        continue

                    # Direct field (has its own T key)
                    if annot.T:
                        field_key = annot.T.strip("()")
                        if field_key in data:
                            raw = data[field_key]
                            if raw is not None:
                                _fill_annotation(annot, raw)

                    # Kid annotation (radio button child — T is on parent)
                    elif annot.Parent and annot.Parent.T:
                        parent_key = annot.Parent.T.strip("()")
                        if parent_key in data and data[parent_key] is not None:
                            # Parent handles the group — skip individual kids here
                            # (parent annotation processed when annot.T is set)
                            pass

        PdfWriter().write(output_pdf, pdf)
        return output_pdf