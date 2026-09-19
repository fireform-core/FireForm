from unittest.mock import MagicMock

from pdfrw import PdfArray, PdfDict, PdfName, PdfReader, PdfWriter

from app.services.filler import Filler


def test_filler_module_imports():
    """Basic sanity check that the PDF filler can be imported."""
    assert Filler is not None


def test_pdf_checkbox_is_recognized_as_btn(tmp_path):
    """A PDF checkbox widget should use the /Btn field type."""
    pdf_path = tmp_path / "checkbox.pdf"

    widget = PdfDict(
        Type=PdfName.Annot,
        Subtype=PdfName.Widget,
        FT=PdfName.Btn,
        T="AcceptTerms",
        Rect=PdfArray([100, 100, 120, 120]),
    )

    page = PdfDict(
        Type=PdfName.Page,
        MediaBox=PdfArray([0, 0, 612, 792]),
        Annots=PdfArray([widget]),
    )

    writer = PdfWriter()
    writer.addpage(page)
    writer.write(str(pdf_path))

    loaded = PdfReader(str(pdf_path))
    annotation = loaded.pages[0].Annots[0]

    assert annotation.FT == PdfName.Btn
    assert str(annotation.T) == "(AcceptTerms)"


def test_filler_checks_checkbox_when_answer_is_true(tmp_path):
    """A checkbox should be checked when the answer is True."""
    pdf_path = tmp_path / "checkbox.pdf"

    widget = PdfDict(
        Type=PdfName.Annot,
        Subtype=PdfName.Widget,
        FT=PdfName.Btn,
        T="AcceptTerms",
        Rect=PdfArray([100, 100, 120, 120]),
    )

    page = PdfDict(
        Type=PdfName.Page,
        MediaBox=PdfArray([0, 0, 612, 792]),
        Annots=PdfArray([widget]),
    )

    writer = PdfWriter()
    writer.addpage(page)
    writer.write(str(pdf_path))

    mock_llm = MagicMock()
    mock_llm.main_loop.return_value.get_data.return_value = {
        "AcceptTerms": True
    }

    output_pdf = Filler().fill_form(str(pdf_path), mock_llm)

    filled_pdf = PdfReader(output_pdf)
    annotation = filled_pdf.pages[0].Annots[0]

    assert annotation.V == PdfName.Yes
    assert annotation.AS == PdfName.Yes


def test_filler_unchecks_checkbox_when_answer_is_false(tmp_path):
    """A checkbox should be unchecked when the answer is False."""
    pdf_path = tmp_path / "checkbox.pdf"

    widget = PdfDict(
        Type=PdfName.Annot,
        Subtype=PdfName.Widget,
        FT=PdfName.Btn,
        T="AcceptTerms",
        Rect=PdfArray([100, 100, 120, 120]),
    )

    page = PdfDict(
        Type=PdfName.Page,
        MediaBox=PdfArray([0, 0, 612, 792]),
        Annots=PdfArray([widget]),
    )

    writer = PdfWriter()
    writer.addpage(page)
    writer.write(str(pdf_path))

    mock_llm = MagicMock()
    mock_llm.main_loop.return_value.get_data.return_value = {
        "AcceptTerms": False
    }

    output_pdf = Filler().fill_form(str(pdf_path), mock_llm)

    filled_pdf = PdfReader(output_pdf)
    annotation = filled_pdf.pages[0].Annots[0]

    assert annotation.V == PdfName.Off
    assert annotation.AS == PdfName.Off


def test_filler_selects_radio_button_option(tmp_path):
    """A radio button should use its option value when selected."""
    pdf_path = tmp_path / "radio.pdf"

    widget = PdfDict(
        Type=PdfName.Annot,
        Subtype=PdfName.Widget,
        FT=PdfName.Btn,
        Ff=32768,
        T="Gender",
        AS=PdfName.Off,
        AP=PdfDict(
            N=PdfDict(
                Male=PdfDict(),
                Off=PdfDict(),
            )
        ),
        Rect=PdfArray([100, 100, 120, 120]),
    )

    page = PdfDict(
        Type=PdfName.Page,
        MediaBox=PdfArray([0, 0, 612, 792]),
        Annots=PdfArray([widget]),
    )

    writer = PdfWriter()
    writer.addpage(page)
    writer.write(str(pdf_path))

    mock_llm = MagicMock()
    mock_llm.main_loop.return_value.get_data.return_value = {
        "Gender": "Male"
    }

    output_pdf = Filler().fill_form(str(pdf_path), mock_llm)

    filled_pdf = PdfReader(output_pdf)
    annotation = filled_pdf.pages[0].Annots[0]

    assert annotation.V == PdfName.Male
    assert annotation.AS == PdfName.Male