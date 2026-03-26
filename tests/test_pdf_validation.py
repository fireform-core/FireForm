"""Tests for Filler field validation, sanitization, and logging."""

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.filler import Filler, _prepare_value_for_pdf


def _make_widget(name="(field_a)", rect=None):
    r = rect or [0, 100, 200, 120]
    return SimpleNamespace(
        Subtype="/Widget",
        T=name,
        Rect=r,
        V=None,
        AP=None,
    )


def _make_pdf_with_widgets(*widgets):
    page = SimpleNamespace(Annots=list(widgets))
    return SimpleNamespace(pages=[page])


class FakeLLM:
    def __init__(self, data, target_fields):
        self._data = data
        self._target_fields = target_fields

    def main_loop(self):
        return self

    def get_data(self):
        return self._data


@pytest.fixture
def filler():
    return Filler()


def test_prepare_skips_none_and_sentinel():
    assert _prepare_value_for_pdf(None, "string", "k")[0] is None
    r, act, _ = _prepare_value_for_pdf("-1", "string", "k")
    assert r is None and act == "skipped"


def test_prepare_coerces_numeric_string_for_number():
    out, act, _ = _prepare_value_for_pdf("0042", "number", "k")
    assert out == "42"
    assert act == "coerced"


def test_prepare_rejects_bad_number():
    out, act, _ = _prepare_value_for_pdf("not-a-number", "number", "k")
    assert out is None and act == "skipped"


def test_prepare_list_joins_with_semicolon():
    out, act, _ = _prepare_value_for_pdf(["a", "b"], "string", "k")
    assert out == "a; b"
    assert act == "ok"


def test_fill_form_writes_valid_string(filler, caplog):
    caplog.set_level(logging.INFO)
    w = _make_widget("(name)")
    pdf = _make_pdf_with_widgets(w)
    llm = FakeLLM({"name": "  Alice  "}, {"name": "string"})

    with patch("src.filler.PdfReader", return_value=pdf):
        with patch("src.filler.PdfWriter"):
            filler.fill_form("dummy.pdf", llm)

    assert w.V == "Alice"


def test_fill_form_skips_invalid_number_logs_warning(filler, caplog):
    caplog.set_level(logging.WARNING)
    w = _make_widget("(n)")
    pdf = _make_pdf_with_widgets(w)
    llm = FakeLLM({"n": "x"}, {"n": "number"})

    with patch("src.filler.PdfReader", return_value=pdf):
        with patch("src.filler.PdfWriter"):
            filler.fill_form("dummy.pdf", llm)

    assert w.V is None
    assert any("Skipped PDF field" in r.message for r in caplog.records)


def test_fill_form_coercion_logs_info(filler, caplog):
    caplog.set_level(logging.INFO)
    w = _make_widget("(n)")
    pdf = _make_pdf_with_widgets(w)
    llm = FakeLLM({"n": "007"}, {"n": "number"})

    with patch("src.filler.PdfReader", return_value=pdf):
        with patch("src.filler.PdfWriter"):
            filler.fill_form("dummy.pdf", llm)

    assert w.V == "7"
    assert any("Coerced PDF field" in r.message for r in caplog.records)


def test_fill_form_fewer_answers_than_widgets_warns(filler, caplog):
    caplog.set_level(logging.WARNING)
    w1, w2 = _make_widget("(a)"), _make_widget("(b)")
    pdf = _make_pdf_with_widgets(w1, w2)
    llm = FakeLLM({"a": "only"}, {"a": "string", "b": "string"})

    with patch("src.filler.PdfReader", return_value=pdf):
        with patch("src.filler.PdfWriter"):
            filler.fill_form("dummy.pdf", llm)

    assert w1.V == "only"
    assert w2.V is None
    assert any("Fewer LLM answers" in r.message for r in caplog.records)
    assert any("No LLM answer for PDF field" in r.message for r in caplog.records)


def test_fill_form_global_index_across_pages(filler):
    w1 = _make_widget("(x)", rect=[0, 50, 10, 60])
    p1 = SimpleNamespace(Annots=[w1])
    w2 = _make_widget("(y)", rect=[0, 50, 10, 60])
    p2 = SimpleNamespace(Annots=[w2])
    pdf = SimpleNamespace(pages=[p1, p2])
    llm = FakeLLM({"a": "1", "b": "2"}, {"a": "string", "b": "string"})

    with patch("src.filler.PdfReader", return_value=pdf):
        with patch("src.filler.PdfWriter"):
            filler.fill_form("dummy.pdf", llm)

    assert w1.V == "1"
    assert w2.V == "2"
