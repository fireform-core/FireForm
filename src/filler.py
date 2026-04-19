# filler.py 
from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
from datetime import datetime
from typing import List


class Filler:
    def __init__(self):
        pass

    def _normalize_field_name(self, name: str) -> str:
        """Remove parentheses, spaces, and lower case for consistent comparison."""
        return name.strip("()").lower().replace(" ", "")

    #a new def to extract things in order
    def _get_field_names_in_order(self, pdf):
        """Extract field names in the order they appear in the PDF."""
        field_names = []
        for page in pdf.pages:
            if not page.Annots:
                continue
            for annot in page.Annots:
                if annot.Subtype == "/Widget" and annot.T:
                    field_names.append(annot.T)
        return field_names

    def fill_form(self, pdf_form: str, llm: LLM, pdf_fields: List[str],definitions: List[str], use_timeline: bool = False):
        #timeline field added
        """
        Fill a PDF form with values extracted by the LLM.
        :param pdf_form: Path to the PDF template.
        :param llm: LLM instance with extracted data.
        :param pdf_fields: List of actual PDF field names (ignored; order is determined from the PDF).
        :param definitions: List of semantic field names (order must match the visual order of fields in the PDF).
        :param use_timeline: If True, also fill narrative/timeline fields.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        #  LLM run
        t2j = llm.main_loop() if not use_timeline else llm.main_loop_with_timeline()
        textbox_answers = t2j.get_data()  # dictionary keyed 

        pdf = PdfReader(pdf_form)

        # Get fields in order and map them 
        ordered_fields = self._get_field_names_in_order(pdf)
        normalized_pdf_to_def = {}
        for i, raw_field_name in enumerate(ordered_fields):
            if i < len(definitions):
                norm = self._normalize_field_name(raw_field_name)
                normalized_pdf_to_def[norm] = definitions[i]

        # Fill normal fields
        for page in pdf.pages:
            if not page.Annots:
                continue

            for annot in page.Annots:
                if annot.Subtype == "/Widget" and annot.T:
                    raw_field_name = annot.T
                    norm_field_name = self._normalize_field_name(raw_field_name)
                    definition = normalized_pdf_to_def.get(norm_field_name)

                    if definition is not None:
                        value = textbox_answers.get(definition)
                        if value is not None and value != "-1":  # here -1 indicates missing
                            annot.V = str(value)
                            annot.AP = None

        # Timeline filling
        if use_timeline:
            timeline = t2j.get_timeline()
            if timeline:
                self._fill_timeline(pdf, timeline)

        PdfWriter().write(output_pdf, pdf)
        return output_pdf

    def _fill_timeline(self, pdf, timeline):
        """Fill narrative/timeline field if present."""
        timeline_text = ""
        for event in timeline:
            ts = event.get("timestamp", "")
            event_type = event.get("event_type", "").upper()
            desc = event.get("description", "")
            loc = event.get("location", "")
            pers = event.get("personnel", "")
            line = f"{ts} - {event_type}: {desc}"
            if loc:
                line += f" | Location: {loc}"
            if pers:
                line += f" | Personnel: {pers}"
            timeline_text += line + "\n"

# the keywords that look out for the in the content for filling
        narrative_keywords = [
            "narrative", "timeline", "description", "summary", "incidentdetails"
        ]
        for page in pdf.pages:
            if not page.Annots:
                continue
            for annot in page.Annots:
                if annot.Subtype == "/Widget" and annot.T:
                    field_name = annot.T.lower().replace(" ", "")
                    if any(keyword in field_name for keyword in narrative_keywords):
                        annot.V = timeline_text
                        annot.AP = None
                        return
