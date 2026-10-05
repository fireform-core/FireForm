"""PDF -> JSON schema for the model.

Tables come from the printed grid (geometry.py), not from widget names, and
every field is described by the tooltip (/TU) the form author gave it.
expand_output() maps the model's table rows back to widget names.
"""

import os
import re

from pypdf import PdfReader

from . import geometry

SIGNATURE_TYPE = 6

TYPE_TO_SCHEMA = {
    0: {"type": "string"},
    1: {"type": "string"},
    2: {"enum": ["Yes", "Off"]},
    3: {"type": "string"},
    4: {"type": "string"},
    5: {"type": "string"},
    6: {"type": "string"},
    7: {"type": "string"},
}


def _sanitize(text):
    """Turn printed column header text into a valid JSON property name."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_")
    return s[:60] if s else "col"


def create_template(pdf_path):
    """(schema, tables, groups) for a fillable PDF.

    schema is what the model fills: geometry tables as arrays, every other
    widget as a scalar, each described by its /TU tooltip. tables and groups
    map array rows back to widget names (expand_output).
    """
    layout = geometry.extract(os.path.abspath(pdf_path))
    all_tables, all_groups, schema = build_schema(layout)
    add_tooltip_descriptions(schema, all_groups, read_tooltips(pdf_path))
    return schema, all_tables, all_groups


def build_schema(layout):
    """(tables, groups, schema) for a geometry.extract() result."""
    # Widget types from layout (signatures already excluded by geometry.extract)
    widget_types = {w["field_name"]: w["field_type"] for w in layout["widgets"]}

    # Track widgets claimed by tables
    table_widget_set = set()

    all_tables = []
    all_groups = {}
    used_col_names = set()

    for ti, geo_table in enumerate(layout["tables"]):
        columns = []
        for ci, col in enumerate(geo_table["columns"]):
            col_name = _sanitize(col["text"])
            base = col_name
            suffix = 1
            while col_name in used_col_names:
                col_name = f"{base}_{suffix}"
                suffix += 1
            used_col_names.add(col_name)

            members = []
            for ri, m in enumerate(col["members"]):
                if m is not None:
                    members.append(m["field_name"])
                    table_widget_set.add(m["field_name"])
                else:
                    members.append(f"__empty_{ti}_{ci}_{ri}__")

            all_groups[col_name] = members
            columns.append(col_name)

            first_real = next((m for m in col["members"] if m is not None), None)
            widget_types[col_name] = first_real["field_type"] if first_real else 7

        all_tables.append({
            "columns": columns,
            "row_count": geo_table["rows"],
            "name": f"resource_summary_{ti}_table",
            "caption": geo_table["caption"],
            "headers": [col["text"] for col in geo_table["columns"]],
        })

    # Scalars: non-table widgets in document order
    singles = [
        w["field_name"]
        for w in layout["widgets"]
        if w["field_name"] not in table_widget_set
    ]

    # Build JSON schema
    properties = {}
    required = []

    for name in singles:
        ft = widget_types.get(name, 7)
        properties[name] = {**TYPE_TO_SCHEMA.get(ft, {"type": "string"}), "description": ""}
        if name not in required:
            required.append(name)

    for table_num, table in enumerate(all_tables):
        row_props = {}
        for col in table["columns"]:
            ft = widget_types.get(col, 7)
            row_props[col] = {
                **TYPE_TO_SCHEMA.get(ft, {"type": "string"}),
                "description": "",
            }
        properties[table["name"]] = {
            "type": "array",
            "description": "",
            "items": {
                "type": "object",
                "properties": row_props,
                "required": list(row_props.keys()),
            },
            "maxItems": table["row_count"],
        }
        required.append(table["name"])

    schema = {"type": "object", "properties": properties, "required": required}
    return all_tables, all_groups, schema


def expand_output(llm_output, tables, groups):
    """Map array rows back to original widget field names."""
    flat = {}

    for table_num, table in enumerate(tables):
        rows = llm_output.get(table["name"], [])
        for i, row in enumerate(rows):
            for col in table["columns"]:
                if col in groups and i < len(groups[col]) and col in row:
                    field_name = groups[col][i]
                    if not field_name.startswith("__empty_"):
                        flat[field_name] = row[col]

    table_names = {table["name"] for table in tables}
    for key, value in llm_output.items():
        if key not in table_names:
            flat[key] = value

    return flat


# ------------------------------------------------------------------ tooltips

ROW_SUFFIX = re.compile(r"[_\s]*Row[_\s]*\d*\s*$", re.IGNORECASE)
ITEM_NUMBER = re.compile(r"^\d+\.\s*")


def clean_tooltip(tooltip, field_name):
    """Tooltip text worth showing: no row suffix, no item number, and blank
    when it only repeats the field name."""
    text = re.sub(r"\s+", " ", (tooltip or "")).strip()
    text = ROW_SUFFIX.sub("", text)
    text = text.rstrip("_ ").strip()
    text = ITEM_NUMBER.sub("", text).strip()
    if not text or text.casefold() == field_name.casefold():
        return ""
    return text


def read_tooltips(pdf_path):
    tooltips = {}
    for page in PdfReader(pdf_path).pages:
        for widget in geometry.page_widgets(page):
            tu = widget.annotation.get("/TU")
            if tu is not None:
                tooltips.setdefault(widget.field_name, str(tu))
    return tooltips


def add_tooltip_descriptions(schema, groups, tooltips):
    """Scalars take their own tooltip; a table column takes its first row's."""
    def describe(key):
        members = groups.get(key)
        if members:
            widget_name = next((m for m in members if not m.startswith("__empty_")), key)
        else:
            widget_name = key
        return clean_tooltip(tooltips.get(widget_name, ""), widget_name)

    for key, prop in schema["properties"].items():
        if "items" in prop:
            for column, column_prop in prop["items"]["properties"].items():
                column_prop["description"] = describe(column)
        else:
            prop["description"] = describe(key)
