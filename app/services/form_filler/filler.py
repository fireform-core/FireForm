"""Narrative + fillable PDF -> filled PDF.

    result = filler.fill("ics_201.pdf", narrative, "ics_201_filled.pdf")

Ollama host, model and timeout come from app.core.config (OLLAMA_HOST,
OLLAMA_MODEL, OLLAMA_TIMEOUT environment variables).

fill() builds the schema (template.py), sends prompt.txt + narrative + schema
to Ollama, maps the answer back to widget names and writes the filled PDF.
It returns every intermediate step so callers (the benchmark) can save them.
"""

import json
import os

import requests
from pypdf import PdfWriter

from app.core.config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT

from . import template
from .geometry import CHECKBOX, RADIOBUTTON, SIGNATURE, drop_null_parents, on_state, page_widgets

OPTIONS = {
    "num_ctx": 32768,
    # Backstop for runaway generation; the largest real output (ICS 209) is ~8k tokens
    "num_predict": 12288,
    "temperature": 0,
    "seed": 42,
    "repeat_penalty": 1.0,
    "repeat_last_n": 0,
}

with open(os.path.join(os.path.dirname(__file__), "prompt.txt"), "r") as f:
    PROMPT = f.read()


def fill(pdf_path, narrative, out_path=None, model=None):
    """Fill pdf_path from the narrative. Writes the PDF when out_path is given.

    Returns {schema, tables, groups, prompt, response_text, values}: the
    schema sent as Ollama's format, the exact prompt, the raw model output,
    and the flat {widget name: value} dict used to fill the PDF.
    """
    schema, tables, groups = template.create_template(pdf_path)
    strip_empty_descriptions(schema["properties"])

    prompt = build_prompt(narrative, schema)
    response_text = call_model(prompt, schema, model or OLLAMA_MODEL)

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


def build_prompt(narrative, schema):
    user_content = (
        "<incident_narrative>\n"
        + narrative
        + "\n</incident_narrative>\n\n<target_json_schema>\n"
        + json.dumps(schema["properties"], indent=2, ensure_ascii=False)
        + "\n</target_json_schema>"
    )
    return PROMPT.rstrip() + "\n\n" + user_content


def call_model(prompt, schema, model):
    """Ollama with the schema as `format`, so the answer always parses into it."""
    payload = {
        "model": model,
        "prompt": prompt,
        "format": schema,
        "stream": False,
        "think": False,
        "options": OPTIONS,
    }
    response = requests.post(
        OLLAMA_HOST + "/api/generate",
        json=payload,
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    return response.json().get("response", "")


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
