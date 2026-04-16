"""
PDF Field Detector Module
=========================
Detects and extracts interactive form field metadata from PDF files.

This module parses PDF annotations (/Annots with /Widget subtypes) to
extract field names, types, and bounding box coordinates. It is the
backend engine that powers the Field Mapping Wizard (Issue #111).

Supported field types:
    - /Tx  → Text (text inputs, text areas)
    - /Btn → Button (checkboxes, radio buttons)
    - /Ch  → Choice (dropdowns, list boxes)

Note: This detector works with digitally created fillable PDFs
(AcroForms). Scanned/image-based PDFs are not supported and would
require OCR integration as a future enhancement.
"""

from pypdf import PdfReader


class PDFFieldDetector:
    """Detects and extracts interactive form field metadata from PDF files.

    Parses each page's /Annots annotations, filters for /Widget subtypes
    (interactive form fields), and extracts:
        - Field name (from the /T key)
        - Field type (/Tx, /Btn, /Ch)
        - Bounding box coordinates (X, Y, Width, Height)

    This data is structured for frontend visual rendering and eventual
    drag-and-drop field mapping.
    """

    FIELD_TYPE_MAP = {
        "/Tx": "Text",
        "/Btn": "Button",
        "/Ch": "Choice",
    }

    def detect_fields(self, pdf_path: str) -> dict:
        """Parse a PDF and return all detected interactive form fields.

        Args:
            pdf_path: Absolute or relative path to the PDF file.

        Returns:
            A dictionary with the following structure::

                {
                    "filename": "form.pdf",
                    "total_pages": 3,
                    "total_fields": 12,
                    "pages": [
                        {
                            "page_number": 1,
                            "fields": [
                                {
                                    "field_name": "Employee Name",
                                    "field_type": "Text",
                                    "raw_type": "/Tx",
                                    "rect": {
                                        "x": 72.0,
                                        "y": 700.0,
                                        "width": 200.0,
                                        "height": 20.0
                                    }
                                }
                            ]
                        }
                    ]
                }

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            Exception: If the PDF cannot be parsed.
        """
        reader = PdfReader(pdf_path)
        filename = pdf_path.split("/")[-1].split("\\")[-1]

        pages = []
        total_fields = 0

        for page_index, page in enumerate(reader.pages):
            page_fields = self._extract_page_fields(page)
            total_fields += len(page_fields)
            pages.append(
                {
                    "page_number": page_index + 1,
                    "fields": page_fields,
                }
            )

        return {
            "filename": filename,
            "total_pages": len(reader.pages),
            "total_fields": total_fields,
            "pages": pages,
        }

    def _extract_page_fields(self, page) -> list:
        """Extract form fields from a single PDF page.

        Args:
            page: A pypdf PageObject.

        Returns:
            A list of field metadata dictionaries. Returns an empty
            list if the page has no annotations or no widget fields.
        """
        annotations = page.get("/Annots")
        if not annotations:
            return []

        fields = []
        for annotation in annotations:
            annotation_obj = annotation.get_object()
            field = self._parse_annotation(annotation_obj)
            if field is not None:
                fields.append(field)

        return fields

    def _parse_annotation(self, annotation) -> dict | None:
        """Parse a single annotation into field metadata.

        Only processes /Widget subtype annotations that have a field
        name (/T key) and a recognized field type (/FT key).

        Args:
            annotation: A resolved PDF annotation dictionary object.

        Returns:
            A field metadata dictionary, or None if the annotation
            is not a recognized interactive form field.
        """
        subtype = annotation.get("/Subtype")
        if subtype != "/Widget":
            return None

        field_name = annotation.get("/T")
        if not field_name:
            return None

        raw_type = annotation.get("/FT", "")
        field_type = self.FIELD_TYPE_MAP.get(raw_type, "Unknown")

        rect = self._extract_rect(annotation)

        return {
            "field_name": str(field_name),
            "field_type": field_type,
            "raw_type": str(raw_type),
            "rect": rect,
        }

    @staticmethod
    def _extract_rect(annotation) -> dict:
        """Extract bounding box coordinates from an annotation's /Rect.

        The PDF /Rect array is [x1, y1, x2, y2] where (x1, y1) is the
        lower-left corner and (x2, y2) is the upper-right corner.
        This method converts it to {x, y, width, height} for easier
        frontend rendering.

        Args:
            annotation: A resolved PDF annotation dictionary object.

        Returns:
            A dictionary with x, y, width, and height. Returns all
            zeros if no /Rect is found.
        """
        rect_array = annotation.get("/Rect")
        if not rect_array or len(rect_array) < 4:
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}

        try:
            x1 = float(rect_array[0])
            y1 = float(rect_array[1])
            x2 = float(rect_array[2])
            y2 = float(rect_array[3])
        except (ValueError, TypeError):
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}

        return {
            "x": round(min(x1, x2), 2),
            "y": round(min(y1, y2), 2),
            "width": round(abs(x2 - x1), 2),
            "height": round(abs(y2 - y1), 2),
        }
