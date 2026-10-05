"""Read a fillable PDF: its widgets (pypdf) and the grid it is printed on (pdfplumber).

A blank government form is a drawn grid, so the row and the column of a
fillable box are a property of the paper, not of the widget's name. extract()
reads the ruling lines, decides which runs of grid rows are logical tables,
and returns every widget with where it sits and what text names it.

    widget = {page, rect, field_name, field_type, tooltip,
              label_left, label_above, label_inside, label_right,
              block,                           # "10. Resource Summary"
              table_id, table_caption, column_header, row_index}
"""
import os
import re
from collections import namedtuple

import pdfplumber
from pypdf import PdfReader
from pypdf.generic import DictionaryObject

# ------------------------------------------------------------- pypdf widgets
# Each widget annotation as (field_name, field_type, rect, annotation).

Widget = namedtuple("Widget", ["field_name", "field_type", "rect", "annotation"])

# Widget type codes
UNKNOWN, BUTTON, CHECKBOX, COMBOBOX, LISTBOX, RADIOBUTTON, SIGNATURE, TEXT = range(8)

# /Ff bits (PDF 32000-1, tables 226 and 230)
FF_RADIO = 1 << 15
FF_PUSHBUTTON = 1 << 16
FF_COMBO = 1 << 17


def _parent(node):
    parent = node.get("/Parent")
    parent = parent.get_object() if parent is not None else None
    return parent if isinstance(parent, DictionaryObject) else None


def _inherited(annotation, key):
    """/FT and /Ff can live on a parent field instead of the widget itself."""
    node = annotation
    while node is not None:
        if key in node:
            return node[key]
        node = _parent(node)
    return None


def _field_name(annotation):
    """Fully qualified name: parent /T values joined with '.'."""
    parts = []
    node = annotation
    while node is not None:
        if "/T" in node:
            parts.append(str(node["/T"]))
        node = _parent(node)
    return ".".join(reversed(parts))


def _field_type(annotation):
    ft = _inherited(annotation, "/FT")
    flags = int(_inherited(annotation, "/Ff") or 0)
    if ft == "/Tx":
        return TEXT
    if ft == "/Sig":
        return SIGNATURE
    if ft == "/Ch":
        return COMBOBOX if flags & FF_COMBO else LISTBOX
    if ft == "/Btn":
        if flags & FF_PUSHBUTTON:
            return BUTTON
        if flags & FF_RADIO:
            return RADIOBUTTON
        return CHECKBOX
    return UNKNOWN


def page_widgets(page):
    """Form widgets on a pypdf page, in /Annots order."""
    widgets = []
    for annot in page.get("/Annots") or []:
        annotation = annot.get_object()
        if annotation.get("/Subtype") != "/Widget":
            continue
        widgets.append(Widget(
            _field_name(annotation),
            _field_type(annotation),
            [float(v) for v in annotation["/Rect"]],
            annotation,
        ))
    return widgets


def drop_null_parents(page):
    """ics_209 has widgets with /Parent null. A null entry means the same as a
    missing one, but pypdf's form filler crashes on it, so remove it."""
    for widget in page_widgets(page):
        node = widget.annotation
        while node is not None:
            if "/Parent" in node and _parent(node) is None:
                del node["/Parent"]
            node = _parent(node)


def on_state(widget):
    """Name of the 'checked' appearance state, e.g. '/Yes'."""
    ap = widget.annotation.get("/AP")
    states = ap.get_object().get("/N") if ap is not None else None
    states = states.get_object() if states is not None else {}
    return next((s for s in states if s != "/Off"), "/Yes")


# --------------------------------------------------------------- geometry

class Rect:
    """Axis-aligned rectangle. Top-left origin, like pdfplumber."""

    def __init__(self, x0, y0=None, x1=None, y1=None):
        if y0 is None:
            x0, y0, x1, y1 = x0
        self.x0, self.y0, self.x1, self.y1 = float(x0), float(y0), float(x1), float(y1)

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0

    def get_area(self):
        return self.width * self.height

    def __iter__(self):
        return iter((self.x0, self.y0, self.x1, self.y1))

    def __repr__(self):
        return f"Rect({self.x0}, {self.y0}, {self.x1}, {self.y1})"


# Ruling lines only, like the old find_tables(strategy="lines")
TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}

# ------------------------------------------------------------------ primitives

CAPTION_RE = re.compile(r"^\s*(\d{1,2})\.\s*\S")
JUNK_TOOLTIP_RE = re.compile(
    r"^(undefined|check\s*box|checkbox|text\s*\d*|text\s*field|button|field)\s*\d*$", re.I)
ROW_TAIL_RE = re.compile(r"[,\s_]*\(?\s*row\s*[_\s]*\d+\s*\)?\s*$", re.I)
INDEX_TAIL_RE = re.compile(r"[\s_\-.#]*\[?\d+\]?$")


def is_signature(w):
    return w.field_type == 6 or "signature" in w.field_name.lower()


def clean(text, limit=90):
    text = re.sub(r"[-]", " ", str(text))     # dingbat checkbox glyphs
    text = re.sub(r"\s+", " ", text).strip(" :.-_•*")
    return text[:limit]


def norm(text):
    """Comparable form of a naming signal: no case, no punctuation, no row tail."""
    t = re.sub(r"[-]", " ", str(text or "")).lower()
    t = ROW_TAIL_RE.sub("", t)
    t = INDEX_TAIL_RE.sub("", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def rect_text(words, rect, limit=90):
    """Printed words whose centre falls inside rect, in reading order."""
    hits = [w for w in words
            if rect.x0 <= (w[0] + w[2]) / 2 <= rect.x1
            and rect.y0 <= (w[1] + w[3]) / 2 <= rect.y1]
    hits.sort(key=lambda w: (round(w[1] / 3), w[0]))
    return clean(" ".join(h[4] for h in hits), limit)


# ------------------------------------------------------------- printed labels
# The text left of, above, inside and right of each widget. The right-hand
# label matters because the only thing that tells a "Yes" checkbox from its
# "No" twin is the word to its right, and that pair is a whole column on ICS 206.

def _blocked(a, b, others):
    lo_x, hi_x = min(a.x0, b.x0), max(a.x1, b.x1)
    lo_y, hi_y = min(a.y0, b.y0), max(a.y1, b.y1)
    for o in others:
        if o.x1 <= lo_x + 1 or o.x0 >= hi_x - 1:
            continue
        if o.y1 <= lo_y + 1 or o.y0 >= hi_y - 1:
            continue
        return True
    return False


def labels_for(rect, words, others):
    above, left, right, inside = [], [], [], []
    for wx0, wy0, wx1, wy1, txt in words:
        wr = Rect(wx0, wy0, wx1, wy1)
        ox = min(wx1, rect.x1) - max(wx0, rect.x0)
        oy = min(wy1, rect.y1) - max(wy0, rect.y0)
        if ox > 1 and oy > 1 and rect.width > 4:
            inside.append((wx0, txt))
        elif ox > 0 and -2 <= rect.y0 - wy1 < 30 and not _blocked(rect, wr, others):
            above.append((round(rect.y0 - wy1), wx0, txt))
        elif oy > 1 and wx1 <= rect.x0 + 2 and rect.x0 - wx1 < 200 \
                and not _blocked(rect, wr, others):
            left.append((rect.x0 - wx1, txt))
        elif oy > 1 and wx0 >= rect.x1 - 2 and wx0 - rect.x1 < 60 \
                and not _blocked(rect, wr, others):
            right.append((wx0 - rect.x1, txt))
    above.sort(key=lambda t: (t[0], t[1]))
    left.sort(key=lambda t: -t[0])
    right.sort()
    inside.sort()
    return {
        "label_above": clean(" ".join(t[2] for t in above), 80),
        "label_left": clean(" ".join(t[1] for t in left[-14:]), 80),
        "label_right": clean(" ".join(t[1] for t in right[:4]), 40),
        "label_inside": clean(" ".join(t[1] for t in inside), 60),
    }


BLOCK_RE = re.compile(r"^\s*(\d{1,2})[.\s]\s*([A-Z][^\n]{2,80})")


def caption_cells(grids, lines):
    """Grid cells that open a numbered section. Which block a widget belongs to
    is then pure geometry -- the lowest caption cell above it that its own x
    range touches -- which is what keeps "7. Operations Section" in ICS 203's
    right page column from claiming the left column's boxes."""
    out = []
    for g in grids:
        for row in g["rows"]:
            for cell, _ in [c for r in [row] + row["subs"] for c in r["cells"]]:
                head = next((ln for ln in lines
                             if cell.y0 - 2 <= ln["rect"].y0 <= cell.y1
                             and cell.x0 - 2 <= ln["rect"].x0 <= cell.x1
                             and BLOCK_RE.match(ln["text"])), None)
                if head:
                    out.append((cell, clean(head["text"], 110)))
    return out


def block_for(rect, captions, lines):
    best = None
    for cell, text in captions:
        if cell.y0 > rect.y0 + 2 or min(cell.x1, rect.x1) - max(cell.x0, rect.x0) <= 0:
            continue
        if best is None or cell.y0 > best[0].y0:
            best = (cell, text)
    if best:
        return best[1]
    above = [ln for ln in lines if ln["rect"].y0 <= rect.y0 + 2 and BLOCK_RE.match(ln["text"])]
    return clean(above[-1]["text"], 110) if above else ""


def page_words(page):
    """(x0, y0, x1, y1, text) words, as MuPDF's get_text("words") gives them.

    pdfplumber sizes each word by its own font, so a bold "4." sits lower than
    the "Name:" beside it and rect_text() reads the row out of order. Words on
    one pdfminer text line share that line's top and bottom instead. Rotated
    headers ("Arrived", "# of Persons") are printed bottom-to-top.
    """
    lines = page.objects.get("textlinehorizontal", [])
    out = []
    for w in page.extract_words(char_dir_rotated="btt"):
        top, bottom = w["top"], w["bottom"]
        cy = (top + bottom) / 2
        line = next((ln for ln in lines
                     if ln["x0"] - 1 <= w["x0"] and w["x1"] <= ln["x1"] + 1
                     and ln["top"] <= cy <= ln["bottom"]), None) if w["upright"] else None
        if line:
            top, bottom = line["top"], line["bottom"]
        out.append((w["x0"], top, w["x1"], bottom, w["text"]))
    return out


def page_lines(page):
    """pdfminer's layout lines (pdfplumber opened with laparams), which split
    side-by-side columns the way MuPDF's text lines do."""
    out = []
    for line in page.objects.get("textlinehorizontal", []):
        txt = line["text"]
        if txt.strip():
            out.append({"rect": Rect(line["x0"], line["top"], line["x1"], line["bottom"]),
                        "text": txt.strip()})
    out.sort(key=lambda item: (round(item["rect"].y0, 1), item["rect"].x0))
    return out


# --------------------------------------------------------------------- the grid

Y_TOL = 1.5


def page_grids(page):
    """Ruling-line grids, each as coarse rows with their nested sub-rows.

    find_tables reports a row for every horizontal rule, so a cell that is
    subdivided (the Yes/No pair inside "Paramedics on Site?") shows up as extra
    rows nested inside the real one. A row wholly inside another is a sub-row:
    it is not a table row, but its cell edges tell us how the parent's columns
    are subdivided.
    """
    grids = []
    for t in page.find_tables(TABLE_SETTINGS):
        rows = []
        for ri, row in enumerate(t.rows):
            cells = [(Rect(c), ci) for ci, c in enumerate(row.cells) if c]
            if cells:
                rows.append({"idx": ri, "y0": row.bbox[1], "y1": row.bbox[3],
                             "cells": cells, "subs": []})
        if not rows:
            continue
        coarse = []
        for r in sorted(rows, key=lambda r: (r["y0"], -(r["y1"] - r["y0"]))):
            host = next((c for c in coarse
                         if c["y0"] <= r["y0"] + Y_TOL and r["y1"] <= c["y1"] + Y_TOL
                         and (c["y1"] - c["y0"]) > (r["y1"] - r["y0"]) + Y_TOL), None)
            if host:
                host["subs"].append(r)
            else:
                coarse.append(r)
        grids.append({"bbox": Rect(t.bbox), "rows": coarse})
    return grids


def page_bands(grid, words):
    """[(x0, x1)] page columns. Two-column layouts (ICS 203, 207) put unrelated
    blocks side by side; a cut only counts when it is a cell edge on most rows
    AND two or more numbered captions start exactly there."""
    rows = grid["rows"]
    gx0, gx1 = grid["bbox"].x0, grid["bbox"].x1
    edges = {}
    for r in rows:
        for x in {round(c.x0) for c, _ in r["cells"]}:
            edges[x] = edges.get(x, 0) + 1
    for x, n in sorted(edges.items(), key=lambda kv: -kv[1]):
        if n < 0.5 * len(rows) or not (gx0 + 0.3 * (gx1 - gx0) < x < gx0 + 0.7 * (gx1 - gx0)):
            continue
        caps = 0
        for r in rows:
            for c, _ in r["cells"]:
                if abs(c.x0 - x) < 2 and CAPTION_RE.match(rect_text(words, c)):
                    caps += 1
        if caps >= 2:
            return [(gx0 - 1, x), (x, gx1 + 1)]
    return [(gx0 - 1, gx1 + 1)]


def classify(row, band, words, widgets):
    """What a grid row is, seen from inside one page column band."""
    cells = [c for c, _ in row["cells"] if band[0] <= (c.x0 + c.x1) / 2 <= band[1]]
    if not cells:
        return None
    cells.sort(key=lambda c: c.x0)
    texts = [rect_text(words, c) for c in cells]
    wid = [w for w in widgets
           if row["y0"] - Y_TOL <= (w["rect"].y0 + w["rect"].y1) / 2 <= row["y1"] + Y_TOL
           and band[0] <= (w["rect"].x0 + w["rect"].x1) / 2 <= band[1]]
    caption = next((t for t in texts if CAPTION_RE.match(t)), "")
    if wid:
        kind = "body"
    elif sum(1 for t in texts if t) >= 2 and len(cells) >= 2:
        kind = "header"
    elif caption:
        kind = "caption"
    elif any(texts):
        kind = "label"
    else:
        kind = "blank"
    return {"row": row, "cells": cells, "texts": texts, "widgets": wid,
            "caption": caption, "kind": kind,
            "label": texts[0] if texts and not CAPTION_RE.match(texts[0]) else ""}


def header_bands(rec, words):
    """Column bands of a header row, split by anything its sub-rows subdivide.

    ICS 204 prints "Resource Identifier | Leader" on a second rule inside the
    "5. Resources Assigned:" cell; ICS 206 prints "Air | Ground" under
    "Travel Time". Both are sub-rows, and both are the real column names.
    """
    bands = []
    for cell, text in zip(rec["cells"], rec["texts"]):
        kids = [c for sub in rec["row"]["subs"] for c, _ in sub["cells"]
                if cell.x0 - 1 <= c.x0 and c.x1 <= cell.x1 + 1 and c.width < cell.width - 2]
        cuts = sorted({round(c.x0, 1) for c in kids} | {round(c.x1, 1) for c in kids}
                      | {round(cell.x0, 1), round(cell.x1, 1)})
        parent = "" if CAPTION_RE.match(text) else text
        if len(cuts) <= 2:
            bands.append({"x0": cell.x0, "x1": cell.x1, "text": parent})
            continue
        for a, b in zip(cuts, cuts[1:]):
            if b - a < 4:
                continue
            kid = next((c for c in kids if abs(c.x0 - a) < 1 and abs(c.x1 - b) < 1), None)
            sub = rect_text(words, kid) if kid is not None else ""
            joined = parent if sub in ("", parent) else f"{parent} {sub}".strip()
            bands.append({"x0": a, "x1": b, "text": clean(joined, 70)})
    return [b for b in bands if b["x1"] - b["x0"] >= 4]


def fits(rec, bands):
    for w in rec["widgets"]:
        cx = (w["rect"].x0 + w["rect"].x1) / 2
        if not any(b["x0"] - 2 <= cx <= b["x1"] + 2 for b in bands):
            return False
    return True


# ------------------------------------------------------------- logical tables

MIN_TABLE_ROWS = 2
MIN_REPEAT_ROWS = 3
X_TOL = 9.0


def split_subcolumns(bands, body):
    """A header band that holds more than one widget per row is really several
    columns: "Paramedics on Site?" is a Yes box beside a No box, "Burn Center"
    is a Yes box above a No box, "Trauma Center" is a checkbox plus a Level.
    Slot them by their position within the row (top to bottom, then left to
    right) and name each slot from the word printed next to it."""
    out = []
    for band in bands:
        per_row = []
        for r in body:
            here = [w for w in r["widgets"]
                    if band["x0"] - 2 <= (w["rect"].x0 + w["rect"].x1) / 2 <= band["x1"] + 2]
            here.sort(key=lambda w: (round(w["rect"].y0 / 6), w["rect"].x0))
            per_row.append(here)
        k = max((len(p) for p in per_row), default=0)
        if k <= 1:
            out.append(dict(band, members=[p[0] if p else None for p in per_row]))
            continue
        if not all(len(p) in (0, k) for p in per_row):      # ragged: fall back to x
            slots = cluster_x([w for p in per_row for w in p])
            index = {id(w): i for i, s in enumerate(slots) for w in s}
            per_row = [[next((w for w in p if index[id(w)] == i), None)
                        for i in range(len(slots))] for p in per_row]
            k = len(slots)
        else:
            per_row = [p + [None] * (k - len(p)) for p in per_row]
        for i in range(k):
            members = [p[i] for p in per_row]
            live = [m for m in members if m]
            side = most_common([m["label_right"] for m in live]) or \
                most_common([m["label_left"] for m in live])
            text = clean(f"{band['text']} {side}".strip(), 70) or f"{band['text']} {i + 1}"
            out.append({"x0": live[0]["rect"].x0, "x1": live[0]["rect"].x1,
                        "text": text, "members": members})
    return dedupe_headers([c for c in out if any(c["members"])])


def dedupe_headers(cols):
    """Two sub-columns of one band can pick up the same neighbouring word
    ("Trauma Center: [x] Yes  Level: ____"). Fall back to what the cells
    themselves are called, which is the only thing left that separates them."""
    seen = {}
    for c in cols:
        seen.setdefault(c["text"], []).append(c)
    for text, group in seen.items():
        if len(group) == 1:
            continue
        for i, c in enumerate(group):
            own = shared_text([m for m in c["members"] if m])
            c["text"] = clean(own, 70) if own else f"{text} {i + 1}"
    return cols


def shared_text(widgets):
    """What the widgets of one column are called, with the row number removed:
    "Trauma Center - Level (Row 1)" -> "Trauma Center - Level"."""
    for key in ("tooltip", "field_name"):
        vals = []
        for w in widgets:
            v = w[key]
            if key == "tooltip" and (not v or JUNK_TOOLTIP_RE.match(v)):
                continue
            vals.append(clean(INDEX_TAIL_RE.sub("", ROW_TAIL_RE.sub("", v)), 70))
        best = most_common(vals)
        if best and len(vals) >= max(1, len(widgets) - 1) and vals.count(best) > len(vals) / 2:
            return best
    return ""


def most_common(values):
    values = [v for v in values if v]
    return max(set(values), key=values.count) if values else ""


def cluster_x(widgets):
    """Group widgets into stacks that share a left edge."""
    stacks = []
    for w in sorted(widgets, key=lambda w: (w["rect"].x0, w["rect"].y0)):
        for s in stacks:
            if abs(s[0]["rect"].x0 - w["rect"].x0) <= X_TOL:
                s.append(w)
                break
        else:
            stacks.append([w])
    return stacks


def ruled_tables(recs, words):
    """header row + the run of body rows underneath it that fits its columns."""
    tables, i = [], 0
    while i < len(recs):
        if recs[i]["kind"] != "header":
            i += 1
            continue
        bands = header_bands(recs[i], words)
        body, j = [], i + 1
        while j < len(recs):
            r = recs[j]
            if r["kind"] != "body" or r["caption"] or not fits(r, bands):
                break
            body.append(r)
            j += 1
        if len(body) >= MIN_TABLE_ROWS and len(bands) >= 1:
            cols = split_subcolumns(bands, body)
            if sum(1 for c in cols if any(c["members"])) >= 1:
                tables.append({"kind": "ruled", "caption": recs[i]["caption"],
                               "columns": cols, "rows": len(body),
                               "y0": recs[i]["row"]["y0"], "y1": body[-1]["row"]["y1"]})
            i = j
            continue
        i += 1
    return tables


def band_signature(rec):
    return [(w["rect"].x0 + w["rect"].x1) / 2 for w in
            sorted(rec["widgets"], key=lambda w: w["rect"].x0)]


def same_columns(a, b):
    return len(a) == len(b) and all(abs(x - y) <= X_TOL for x, y in zip(a, b))


def repeat_tables(recs, used):
    """Runs of consecutive body rows that carry the same row label and the same
    widget columns. This is how ICS 203 writes its Division/Group lists: no
    header row, just the words "Division/Group" repeated down the left edge,
    five rows to a branch."""
    tables, i = [], 0
    while i < len(recs):
        r = recs[i]
        if r["kind"] != "body" or r["caption"] or any(taken(w, used) for w in r["widgets"]):
            i += 1
            continue
        sig, lab = band_signature(r), norm(r["label"])
        j = i + 1
        while j < len(recs) and recs[j]["kind"] == "body" and not recs[j]["caption"] \
                and same_columns(band_signature(recs[j]), sig) and norm(recs[j]["label"]) == lab \
                and not any(taken(w, used) for w in recs[j]["widgets"]):
            j += 1
        run = recs[i:j]
        if len(run) >= MIN_REPEAT_ROWS and len(sig) >= 1:
            cols = []
            for k in range(len(sig)):
                members = [sorted(x["widgets"], key=lambda w: w["rect"].x0)[k] for x in run]
                cols.append({"x0": members[0]["rect"].x0, "x1": members[0]["rect"].x1,
                             "text": r["label"] or clean(shared_text(members), 70),
                             "members": members})
            tables.append({"kind": "repeat", "caption": "", "columns": dedupe_headers(cols),
                           "rows": len(run), "y0": run[0]["row"]["y0"],
                           "y1": run[-1]["row"]["y1"]})
            i = j
            continue
        i += 1
    return tables


def loose_tables(widgets, used):
    """Tables drawn without rules, inside one big merged cell: ICS 204 block 8,
    ICS 202's "Other Attachments". Stacks of 3+ widgets at the same x whose
    rows line up across stacks. A stack whose cells carry DIFFERENT printed
    labels is not a column -- that is an org chart or a checklist (ICS 207's
    unit leaders, ICS 202's "ICS 203 / ICS 204 / ..."), where each box means
    something of its own."""
    cols = []
    free = [w for w in widgets if not taken(w, used)]
    for block in dict.fromkeys(w["block"] for w in free):
        # one numbered block at a time: an unruled table never spans two
        for s in cluster_x([w for w in free if w["block"] == block]):
            s.sort(key=lambda w: w["rect"].y0)
            if len(s) >= MIN_REPEAT_ROWS and len({identity(w) for w in s}) == 1:
                cols.append(s)

    tables = []
    for col in sorted(cols, key=lambda c: c[0]["rect"].x0):
        for t in tables:
            if len(t["columns"][0]["members"]) != len(col):
                continue
            if all(abs(a["rect"].y0 - b["rect"].y0) < 6
                   for a, b in zip(t["columns"][0]["members"], col)):
                t["columns"].append({"x0": col[0]["rect"].x0, "x1": col[0]["rect"].x1,
                                     "text": col_text(col), "members": col})
                break
        else:
            tables.append({"kind": "loose", "caption": col[0]["block"],
                           "columns": [{"x0": col[0]["rect"].x0, "x1": col[0]["rect"].x1,
                                        "text": col_text(col), "members": col}],
                           "rows": len(col),
                           "y0": col[0]["rect"].y0, "y1": col[-1]["rect"].y1})
    return tables


def row_lists(widgets, used):
    """A row of three or more identical, evenly spaced boxes with nothing to
    tell them apart is a list, not three fields: ICS 207 prints four blank
    boxes side by side for "however many operations elements you have". The
    schema wants one repeated key, so the run becomes a one-column table."""
    tables = []
    free = [w for w in widgets if not taken(w, used)]
    for block in dict.fromkeys(w["block"] for w in free):
        here = sorted((w for w in free if w["block"] == block),
                      key=lambda w: (round(w["rect"].y0 / 6), w["rect"].x0))
        run = []
        for w in here + [None]:
            same = run and w is not None and abs(w["rect"].y0 - run[-1]["rect"].y0) < 6 \
                and abs(w["rect"].width - run[-1]["rect"].width) < 2 \
                and identity(w) == identity(run[-1])
            if same:
                run.append(w)
                continue
            if len(run) >= MIN_REPEAT_ROWS:
                tables.append({"kind": "row_list", "caption": block,
                               "columns": [{"x0": run[0]["rect"].x0, "x1": run[-1]["rect"].x1,
                                            "text": col_text(run) or block, "members": list(run)}],
                               "rows": len(run), "y0": run[0]["rect"].y0,
                               "y1": run[-1]["rect"].y1})
            run = [w] if w is not None else []
    return tables


def identity(w):
    """What distinguishes this box from its neighbours, ignoring row numbers."""
    return norm(w["tooltip"] if not JUNK_TOOLTIP_RE.match(w["tooltip"] or "") else "") \
        or norm(w["label_left"] or w["label_right"] or w["label_above"]) \
        or norm(w["field_name"])


def col_text(col):
    """An unruled column has no printed heading of its own, so the name the
    cells share is the best description of it."""
    return shared_text(col) or most_common([w["label_above"] for w in col]) \
        or most_common([w["label_left"] for w in col]) or ""



# -------------------------------------------------------------------- extract

def extract(pdf_path, use_tooltips=True):
    doc = pdfplumber.open(pdf_path, laparams={})
    reader = PdfReader(pdf_path)
    all_widgets, all_tables = [], []
    for pno, page in enumerate(doc.pages):
        words = page_words(page)
        lines = page_lines(page)
        raw = [w for w in page_widgets(reader.pages[pno]) if not is_signature(w)]
        # pypdf rects are bottom-left origin; flip to pdfplumber's top-left
        top = float(reader.pages[pno].cropbox.top)
        left = float(reader.pages[pno].cropbox.left)
        rects = [Rect(x0 - left, top - y1, x1 - left, top - y0)
                 for x0, y0, x1, y1 in (w.rect for w in raw)]
        grids = page_grids(page)
        captions = caption_cells(grids, lines)
        widgets = []
        for i, (w, rect) in enumerate(zip(raw, rects)):
            tip = str(w.annotation.get("/TU", ""))
            rec = {"page": pno + 1, "rect": [round(v, 1) for v in rect],
                   "field_name": w.field_name, "field_type": w.field_type,
                   "tooltip": clean(tip, 90) if use_tooltips else "",
                   "block": block_for(rect, captions, lines),
                   "table_id": None, "table_caption": "", "column_header": "",
                   "row_index": None}
            rec.update(labels_for(rect, words, [r for j, r in enumerate(rects) if j != i]))
            rec["_rect"] = rect
            rec["rect"] = rect
            widgets.append(rec)

        page_tables = []
        used = set()
        for gi, grid in enumerate(grids):
            for band in page_bands(grid, words):
                recs = [r for r in (classify(row, band, words, widgets)
                                    for row in grid["rows"]) if r]
                found = ruled_tables(recs, words)
                mark(found, used)
                rep = repeat_tables(recs, used)
                mark(rep, used)
                page_tables += found + rep
        loose = loose_tables(widgets, used)
        mark(loose, used)
        lists = row_lists(widgets, used)
        mark(lists, used)
        page_tables += loose + lists

        for t in page_tables:
            t["page"] = pno + 1
        all_tables += page_tables
        all_widgets += widgets
    doc.close()

    for ti, t in enumerate(sorted(all_tables, key=lambda t: (t["page"], t["y0"], t["columns"][0]["x0"]))):
        t["id"] = ti
        if not t["caption"]:
            t["caption"] = most_common([m["block"] for c in t["columns"]
                                        for m in c["members"] if m])
        for ci, col in enumerate(t["columns"]):
            for ri, m in enumerate(col["members"]):
                if m is None:
                    continue
                m["table_id"] = ti
                m["table_caption"] = t["caption"]
                m["column_header"] = col["text"]
                m["row_index"] = ri + 1
    all_tables.sort(key=lambda t: t["id"])

    return {"form": os.path.basename(pdf_path)[:-4],
            "widgets": all_widgets, "tables": all_tables}


def taken(widget, used):
    return id(widget) in used


def mark(tables, used):
    for t in tables:
        for c in t["columns"]:
            for m in c["members"]:
                if m is not None:
                    used.add(id(m))



