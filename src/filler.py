from pdfrw import PdfReader, PdfWriter, PdfName
from src.llm import LLM
from datetime import datetime


TRUTHY_VALUES = {"yes", "true", "1", "on", "checked", "x", "selected", "male", "female"}
FALSY_VALUES  = {"no", "false", "0", "off", "unchecked", "", "none", "null"}


def _resolve_checkbox_value(raw_value, annot):
    """Convert LLM string → correct PDF checkbox value (/Yes or /Off)."""
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
    """Determine if THIS radio kid should be selected."""
    normalized = str(raw_value).strip().lower()
    try:
        parent = annot.Parent
        if parent and parent.Opt:
            opts = [str(o).strip("()").lower() for o in parent.Opt]
            if kid_index < len(opts) and opts[kid_index] == normalized:
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
    """Return 'text', 'checkbox', 'radio', 'dropdown', 'pushbutton', or 'other'."""
    ft = str(annot.FT).strip("/") if annot.FT else ""
    if ft == "Btn":
        try:
            ff = int(str(annot.Ff)) if annot.Ff else 0
            if ff & (1 << 16):
                return "pushbutton"
            if ff & (1 << 15):
                return "radio"
        except Exception:
            pass
        return "checkbox"
    elif ft == "Tx":
        return "text"
    elif ft == "Ch":
        return "dropdown"
    return "other"


def _fill_annotation(annot, raw_value) -> str:
    """Write correct value to annotation based on field type and return the written value for logging."""
    field_type = _get_field_type(annot)
    written_val = ""

    if field_type == "checkbox":
        annot.V  = _resolve_checkbox_value(raw_value, annot)
        annot.AS = annot.V
        written_val = str(annot.V)

    elif field_type == "radio":
        if annot.Kids:
            normalized = str(raw_value).strip().lower()
            selected_index = None
            try:
                if annot.Opt:
                    opts = [str(o).strip("()").lower() for o in annot.Opt]
                    if normalized in opts:
                        selected_index = opts.index(normalized)
            except Exception:
                pass
            
            for i, kid in enumerate(annot.Kids):
                kid_on_key = None
                try:
                    if kid.AP and kid.AP.N:
                        for key in kid.AP.N.keys():
                            clean = str(key).strip("/")
                            if clean.lower() not in ("off", "false", "0"):
                                kid_on_key = clean
                                break
                except Exception:
                    pass

                # Match by explicit /Opt index, OR by direct match to the internal graphic key!
                if (selected_index is not None and i == selected_index) or \
                   (kid_on_key and normalized in kid_on_key.lower()):
                    on_val = PdfName(kid_on_key if kid_on_key else str(i))
                    kid.AS = on_val
                    annot.V = on_val
                    written_val = str(on_val)
                else:
                    kid.AS = PdfName("Off")
        else:
            annot.V  = _resolve_checkbox_value(raw_value, annot)
            annot.AS = annot.V
            written_val = str(annot.V)

    elif field_type == "pushbutton":
        written_val = "Skipped"

    elif field_type == "dropdown":
        annot.V = "" if raw_value is None else str(raw_value)
        written_val = str(annot.V)

    else:
        # Plain text — never write literal "None"
        annot.V = "" if raw_value is None else str(raw_value)
        annot.AP = None  # Moved inside text block! Checkboxes preserve appearance!
        written_val = str(annot.V)

    return written_val


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form using LLM extraction.
        Uses KEY-BASED matching — field name from PDF matched to
        extracted JSON key. This ensures correct data goes to
        correct field regardless of PDF field order.
        Falls back to positional if key not found in extraction.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        t2j = llm.main_loop()
        extracted = t2j.get_data()  # dict: {field_name: value}

        print(f"[FILLER] Extracted {len(extracted)} fields:")
        for k, v in extracted.items():
            print(f"  {k}: {v}")

        pdf = PdfReader(pdf_form)

        processed_parents = set()

        for page in pdf.pages:
            if page.Annots:
                for annot in page.Annots:
                    if annot.Subtype != "/Widget":
                        continue

                    # Direct field (has its own T key)
                    if annot.T:
                        # Clean field key — strip pdfrw parentheses
                        field_key = annot.T.strip("()")

                        # Try exact key match first
                        raw = extracted.get(field_key)

                        # Try case-insensitive match if exact fails
                        if raw is None:
                            for k, v in extracted.items():
                                if k.lower() == field_key.lower():
                                    raw = v
                                    break

                        if raw is not None:
                            written_val = _fill_annotation(annot, raw)
                            print(f"  [FILLER] Filling '{field_key}' = {raw}  → {written_val} \u2713")
                        else:
                            print(f"  [FILLER] No match for '{field_key}' — leaving empty")

                    # Radio button kid (T key is on the parent)
                    elif annot.Parent and annot.Parent.T:
                        parent = annot.Parent
                        if id(parent) in processed_parents:
                            continue
                        processed_parents.add(id(parent))

                        field_key = parent.T.strip("()")
                        raw = extracted.get(field_key)
                        if raw is None:
                            for k, v in extracted.items():
                                if k.lower() == field_key.lower():
                                    raw = v
                                    break

                        if raw is not None:
                            written_val = _fill_annotation(parent, raw)
                            print(f"  [FILLER] Filling '{field_key}' = {raw}  → {written_val} \u2713")
                        else:
                            print(f"  [FILLER] No match for parent '{field_key}' — leaving empty")

        PdfWriter().write(output_pdf, pdf)
        print("\nlog extracted successfully")
        print(f"along with what it extracted accordingly, pdf file : {output_pdf}")
        return output_pdf

    def fill_form_with_data(self, pdf_form: str, data: dict) -> str:
        """
        Fill a PDF form with pre-extracted data dictionary.
        Used by batch endpoint — NO LLM call.
        Key-based matching with case-insensitive fallback.
        """
        print(f"[log extracted successfully] Found {len(data)} fields mapped from Data Lake.")
        
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        pdf = PdfReader(pdf_form)

        processed_parents = set()

        for page in pdf.pages:
            if page.Annots:
                for annot in page.Annots:
                    if annot.Subtype != "/Widget":
                        continue

                    if annot.T:
                        field_key = annot.T.strip("()")

                        # Exact match
                        raw = data.get(field_key)

                        # Case-insensitive fallback
                        if raw is None:
                            for k, v in data.items():
                                if k.lower() == field_key.lower():
                                    raw = v
                                    break

                        if raw is not None:
                            written_val = _fill_annotation(annot, raw)
                            print(f"  [FILLER] Filling '{field_key}' = {raw}  → {written_val} \u2713")

                    elif annot.Parent and annot.Parent.T:
                        parent = annot.Parent
                        if id(parent) in processed_parents:
                            continue
                        processed_parents.add(id(parent))

                        field_key = parent.T.strip("()")
                        raw = data.get(field_key)
                        if raw is None:
                            for k, v in data.items():
                                if k.lower() == field_key.lower():
                                    raw = v
                                    break

                        if raw is not None:
                            written_val = _fill_annotation(parent, raw)
                            print(f"  [FILLER] Filling '{field_key}' = {raw}  → {written_val} \u2713")

        PdfWriter().write(output_pdf, pdf)
        print("\nlog extracted successfully")
        print(f"along with what it extracted accordingly, pdf file : {output_pdf}")
        return output_pdf