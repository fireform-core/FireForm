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

    def fill_static_pdf(self, pdf_form: str, coordinates: list, data: dict) -> str:
        """
        Fill a static (non-fillable) PDF using the reportlab overlay + PageMerge
        technique (proven approach from PR #70).

        Coordinates come from the Data Lake (FormFieldCoordinates) as percentages.
        We convert back to absolute PDF points and draw text on a transparent
        reportlab canvas, then merge it onto the original page.

        coordinates: list of FormFieldCoordinates (from DB)
        data: dictionary of extracted values (from Data Lake + Semantic Mapper)
        """
        import io
        from pdfrw import PdfReader as PdfrwReader, PdfWriter as PdfrwWriter, PageMerge
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch

        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_static_filled.pdf"
        )

        original_pdf = PdfrwReader(pdf_form)

        # Group coordinates by page
        page_fields: dict[int, list] = {}
        for coord in coordinates:
            pg = coord.page_number
            if pg not in page_fields:
                page_fields[pg] = []
            page_fields[pg].append(coord)

        for page_num, page in enumerate(original_pdf.pages):
            if page_num not in page_fields:
                continue

            # Get page dimensions from the original PDF
            # pdfrw stores MediaBox as [x0, y0, x1, y1]
            media_box = page.MediaBox
            if media_box:
                page_w = float(media_box[2]) - float(media_box[0])
                page_h = float(media_box[3]) - float(media_box[1])
            else:
                page_w = 612  # default letter width
                page_h = 792  # default letter height

            # Create a transparent overlay canvas for this page
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=(page_w, page_h))
            c.setFont("Helvetica", 10)
            c.setFillColorRGB(0, 0, 0)  # Black text

            fields_filled = 0

            for coord in page_fields[page_num]:
                # Match data (case-insensitive fallback)
                raw_val = data.get(coord.field_label)
                if raw_val is None:
                    for k, v in data.items():
                        if k.lower() == coord.field_label.lower():
                            raw_val = v
                            break

                if raw_val is None or str(raw_val).strip() == "":
                    continue

                val_str = str(raw_val).strip()

                # Convert percentages (0-100) back to absolute PDF points
                x_pts = (coord.x / 100.0) * page_w
                y_pts_from_top = (coord.y / 100.0) * page_h
                w_pts = (coord.width / 100.0) * page_w

                # CRITICAL: reportlab uses BOTTOM-LEFT origin
                y_reportlab = page_h - y_pts_from_top

                # Use Paragraph to support word-wrapping and newlines natively
                from reportlab.platypus import Paragraph
                from reportlab.lib.styles import getSampleStyleSheet
                style = getSampleStyleSheet()["Normal"]
                style.fontName = "Helvetica"
                style.fontSize = 10
                style.leading = 12
                
                # If width is 0 or extremely small due to edge scanning, give it a default reasonable width
                avail_w = w_pts if w_pts > 40 else 250

                html_val = val_str.replace("\n", "<br/>")
                p = Paragraph(html_val, style)
                
                # Wrap computes how much actual box height (bh) the text needs
                bw, bh = p.wrap(avail_w, page_h)  
                
                # drawOn places the very bottom of the paragraph. 
                # Since y_reportlab is the top of our field boundary, we subtract bh to anchor it below.
                draw_y = y_reportlab - bh
                p.drawOn(c, x_pts, draw_y)

                fields_filled += 1
                print(f"  [OVERLAY] '{coord.field_label}' (WRAP w={avail_w:.0f}pt) → {val_str[:30]}... at ({x_pts:.1f}, {draw_y:.1f})")

            c.save()
            packet.seek(0)

            # Merge the overlay onto the original page
            overlay_pdf = PdfrwReader(packet)
            if len(overlay_pdf.pages) > 0:
                PageMerge(page).add(overlay_pdf.pages[0]).render()

            print(f"  [PAGE {page_num}] Filled {fields_filled} fields via overlay")

        PdfrwWriter().write(output_pdf, original_pdf)
        print(f"\n[STATIC FILL] Output: {output_pdf}")
        return output_pdf