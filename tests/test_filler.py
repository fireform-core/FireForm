from src.filler import Filler


class DummyT2J:
    def __init__(self, data):
        self._data = data

    def get_data(self):
        return self._data


class DummyLLM:
    def __init__(self, data):
        self._data = data

    def main_loop(self):
        return DummyT2J(self._data)


class DummyAnnot:
    def __init__(self, rect, name):
        self.Rect = rect
        self.Subtype = "/Widget"
        self.T = name
        self.V = None
        self.AP = "placeholder"


class DummyPage:
    def __init__(self, annots):
        self.Annots = annots


class DummyPdf:
    def __init__(self, pages):
        self.pages = pages


class CaptureWriter:
    written = None

    def write(self, output_pdf, pdf):
        CaptureWriter.written = (output_pdf, pdf)


def test_fill_form_keeps_index_across_pages(monkeypatch):
    # One text widget per page to validate index continuity across pages.
    page_1 = DummyPage([DummyAnnot([0, 200, 100, 220], "(field_1)")])
    page_2 = DummyPage([DummyAnnot([0, 200, 100, 220], "(field_2)")])
    dummy_pdf = DummyPdf([page_1, page_2])

    monkeypatch.setattr("src.filler.PdfReader", lambda _: dummy_pdf)
    monkeypatch.setattr("src.filler.PdfWriter", lambda: CaptureWriter())

    llm = DummyLLM({"field_1": "alpha", "field_2": "bravo"})
    output_path = Filler().fill_form("sample.pdf", llm)

    assert output_path.endswith("_filled.pdf")
    assert page_1.Annots[0].V == "alpha"
    assert page_2.Annots[0].V == "bravo"
    assert CaptureWriter.written is not None
