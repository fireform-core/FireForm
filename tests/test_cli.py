"""Tests for the FireForm Typer CLI."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from src.cli import app

runner = CliRunner()


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "extract" in result.stdout


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "fireform" in result.stdout.lower() or "python" in result.stdout.lower()


def test_doctor_ollama_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_cm = MagicMock()
    mock_conn = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=None)

    with patch("src.cli.requests.get", return_value=mock_resp):
        with patch("src.cli.engine.connect", return_value=mock_cm):
            result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Ollama OK" in result.stdout or "pdfrw" in result.stdout


def test_extract_mocked_llm(tmp_path: Path):
    transcript = tmp_path / "t.txt"
    transcript.write_text("hello world", encoding="utf-8")
    fields = tmp_path / "f.json"
    fields.write_text('{"a": "string"}', encoding="utf-8")

    mock_llm = MagicMock()
    mock_llm.get_data.return_value = {"a": "extracted"}

    with patch("src.cli.LLM", return_value=mock_llm):
        result = runner.invoke(
            app,
            ["extract", str(transcript), "--fields", str(fields)],
        )
    assert result.exit_code == 0
    mock_llm.main_loop.assert_called_once()
    assert "extracted" in result.stdout


def test_fill_mocked_filler(tmp_path: Path):
    data = tmp_path / "d.json"
    data.write_text('{"a": "test"}', encoding="utf-8")
    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    mock_llm = MagicMock()
    mock_llm.get_data.return_value = {"a": "test"}
    out_path = str(tmp_path / "filled.pdf")

    with patch("src.cli.LLM", return_value=mock_llm):
        with patch("src.cli.Filler") as mock_cls:
            mock_cls.return_value.fill_form.return_value = out_path
            result = runner.invoke(app, ["fill", str(data), str(pdf)])
    assert result.exit_code == 0
    assert out_path in result.stdout
    mock_cls.return_value.fill_form.assert_called_once()
    call_kw = mock_cls.return_value.fill_form.call_args
    assert call_kw.kwargs.get("skip_extraction") is True


def test_pipeline_mocked(tmp_path: Path):
    tr = tmp_path / "t.txt"
    tr.write_text("text", encoding="utf-8")
    pdf = tmp_path / "f.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    fields = tmp_path / "fields.json"
    fields.write_text('{"x": "string"}', encoding="utf-8")

    mock_llm = MagicMock()
    mock_llm.get_data.return_value = {"x": "y"}
    out_pdf = str(tmp_path / "out.pdf")

    with patch("src.cli.LLM", return_value=mock_llm):
        with patch("src.cli.Filler") as mock_fill_cls:
            mock_fill_cls.return_value.fill_form.return_value = out_pdf
            result = runner.invoke(
                app,
                ["pipeline", str(tr), str(pdf), "--fields", str(fields)],
            )
    assert result.exit_code == 0
    assert mock_llm.main_loop.call_count >= 1
    assert mock_fill_cls.return_value.fill_form.called
    assert out_pdf in result.stdout
