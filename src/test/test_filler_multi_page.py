from src.filler import Filler


class DummyAnnot:
    def __init__(self, x, y):
        self.Subtype = "/Widget"
        self.T = "(field)"
        self.Rect = [str(x), str(y), str(x + 10), str(y + 10)]
        self.V = None
        self.AP = "placeholder"


class DummyPage:
    def __init__(self, annots):
        self.Annots = annots


class DummyPdf:
    def __init__(self, pages):
        self.pages = pages


class DummyWriter:
    def write(self, output_pdf, pdf):
        return None


class DummyLLM:
    def __init__(self, data):
        self._data = data

    def main_loop(self):
        return self

    def get_data(self):
        return self._data


def test_fill_form_keeps_value_index_across_pages(monkeypatch):
    page_one_annot = DummyAnnot(0, 100)
    page_two_annot = DummyAnnot(0, 100)
    dummy_pdf = DummyPdf([DummyPage([page_one_annot]), DummyPage([page_two_annot])])

    monkeypatch.setattr("src.filler.PdfReader", lambda *_args, **_kwargs: dummy_pdf)
    monkeypatch.setattr("src.filler.PdfWriter", lambda: DummyWriter())

    llm = DummyLLM({"field1": "value-1", "field2": "value-2"})
    filler = Filler()

    filler.fill_form("form.pdf", llm)

    assert page_one_annot.V == "value-1"
    assert page_two_annot.V == "value-2"
