"""Narrative + fillable PDF -> filled PDF.

    result = filler.fill("ics_201.pdf", narrative, "ics_201_filled.pdf")

Which LLM answers is picked per call (provider, model), defaulting to
LLM_PROVIDER and LLM_MODEL. See app/services/llm.

fill() builds the schema (template.py), sends prompt.txt + narrative + schema
to the LLM, maps the answer back to widget names and writes the filled PDF.
It returns every intermediate step so callers (the benchmark) can save them.
"""

import json
import os

from pypdf import PdfWriter

from app.services import llm

from . import template
from .geometry import CHECKBOX, RADIOBUTTON, SIGNATURE, drop_null_parents, on_state, page_widgets

with open(os.path.join(os.path.dirname(__file__), "prompt.txt"), "r") as f:
    PROMPT = f.read()


def fill(pdf_path, narrative, out_path=None, model=None, description="", provider=None, registry=None):
    """Fill pdf_path from the narrative. Writes the PDF when out_path is given.

    Returns {schema, tables, groups, prompt, response_text, values}: the
    schema sent to the LLM, the exact prompt, the raw model output,
    and the flat {widget name: value} dict used to fill the PDF.
    """
    schema, tables, groups = template.create_template(pdf_path)
    strip_empty_descriptions(schema["properties"])

    prompt = build_prompt(narrative, schema, description)
    response_text = call_model(prompt, schema, model, provider, registry=registry)

    # Tables come back as arrays of rows; map them to widget names
    values = template.expand_output(json.loads(response_text), tables, groups)

    if out_path:
        write_pdf(pdf_path, values, out_path)

    return {
        "schema": schema,
        "tables": tables,
        "groups": groups,
        "prompt": prompt,
        "response_text": response_text,
        "values": values,
    }


def strip_empty_descriptions(props):
    for prop in props.values():
        if prop.get("description") == "":
            del prop["description"]
        if "items" in prop:
            strip_empty_descriptions(prop["items"]["properties"])
    return props


def build_prompt(narrative, schema, description=""):
    # Omitted entirely when blank so the model is not handed an empty block.
    context = f"<template_description>\n{description}\n</template_description>\n\n" if description else ""
    user_content = (
        context
        + "<incident_narrative>\n"
        + narrative
        + "\n</incident_narrative>\n\n<target_json_schema>\n"
        + json.dumps(schema["properties"], indent=2, ensure_ascii=False)
        + "\n</target_json_schema>"
    )
    return PROMPT.rstrip() + "\n\n" + user_content


def call_model(prompt, schema, model=None, provider=None, registry=None):
    """The answer as JSON text shaped by the schema. None falls back to the defaults."""
    active_registry = registry or llm.get_registry()
    return active_registry.generate_json(prompt, schema, provider, model)


def write_pdf(pdf_path, values, out_path):
    new_doc = PdfWriter(clone_from=pdf_path)

    # pypdf sets checkboxes by appearance-state name ("/Yes"), not "Yes"
    for page in new_doc.pages:
        drop_null_parents(page)
        page_values = {}
        for widget in page_widgets(page):
            if widget.field_type == SIGNATURE:
                continue
            value = values.get(widget.field_name, "")
            if widget.field_type in (CHECKBOX, RADIOBUTTON):
                value = on_state(widget) if value == "Yes" else "/Off"
            page_values[widget.field_name] = "" if value is None else str(value)
        if page_values:
            new_doc.update_page_form_field_values(page, page_values)

    new_doc.write(out_path)
