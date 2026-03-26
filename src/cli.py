"""FireForm unified CLI (Typer)."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

import requests
import typer
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from api.db.database import engine
from api.db.repositories import get_template, list_templates
from src.file_manipulator import FileManipulator
from src.filler import Filler
from src.llm import LLM

app = typer.Typer(
    name="fireform",
    help="FireForm developer CLI: LLM extraction, PDF filling, and templates.",
    add_completion=True,
)
template_app = typer.Typer(help="List or create PDF templates (DB + files).")
app.add_typer(template_app, name="template")


def _configure_logging(verbose: bool, quiet: bool) -> None:
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )


@app.callback()
def global_options(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Only warnings and errors"),
) -> None:
    if verbose and quiet:
        typer.echo("Use either --verbose or --quiet, not both.", err=True)
        raise typer.Exit(1)
    _configure_logging(verbose, quiet)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        typer.echo(f"Invalid JSON or unreadable file {path}: {e}", err=True)
        raise typer.Exit(1) from e


@app.command("extract")
def extract_cmd(
    transcript_file: Path = typer.Argument(..., exists=True, readable=True, help="Plain-text transcript"),
    fields: Path = typer.Option(
        ...,
        "--fields",
        "-f",
        help="JSON object: field name -> type (e.g. string, number, email)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write extracted JSON to this file (still prints to stdout unless --stdout-only)",
    ),
    stdout_only: bool = typer.Option(
        False,
        "--stdout-only",
        help="Print JSON only to stdout (ignore --output)",
    ),
) -> None:
    """Run Ollama extraction on a transcript and print JSON."""
    transcript_text = transcript_file.read_text(encoding="utf-8")
    field_types = _load_json(fields)
    if not isinstance(field_types, dict):
        typer.echo("--fields JSON must be an object", err=True)
        raise typer.Exit(1)

    llm = LLM(transcript_text=transcript_text, target_fields=field_types, json={})
    llm.main_loop()
    data = llm.get_data()
    text_out = json.dumps(data, indent=2, ensure_ascii=False)
    if not stdout_only and output:
        output.write_text(text_out, encoding="utf-8")
        typer.echo(f"Wrote {output}", err=True)
    typer.echo(text_out)


@app.command("fill")
def fill_cmd(
    data_json: Path = typer.Argument(..., exists=True, readable=True, help="JSON object of field -> value"),
    pdf_template: Path = typer.Argument(..., exists=True, readable=True, help="Fillable PDF template path"),
    fields: Optional[Path] = typer.Option(
        None,
        "--fields",
        "-f",
        help="Optional JSON object of field name -> type (defaults to string per key in data)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output filled PDF path (default: timestamped next to template)",
    ),
) -> None:
    """Fill a PDF using precomputed JSON (no Ollama)."""
    raw = _load_json(data_json)
    if not isinstance(raw, dict):
        typer.echo("Data JSON must be an object", err=True)
        raise typer.Exit(1)
    data: dict[str, Any] = raw

    if fields:
        field_types = _load_json(fields)
        if not isinstance(field_types, dict):
            typer.echo("--fields JSON must be an object", err=True)
            raise typer.Exit(1)
    else:
        field_types = {k: "string" for k in data.keys()}

    llm = LLM(transcript_text="", target_fields=field_types, json=data)
    filler = Filler()
    out = filler.fill_form(
        str(pdf_template),
        llm,
        skip_extraction=True,
        output_pdf=str(output) if output else None,
    )
    typer.echo(out)


@app.command("pipeline")
def pipeline_cmd(
    transcript_file: Path = typer.Argument(..., exists=True, readable=True),
    pdf_template: Path = typer.Argument(..., exists=True, readable=True),
    fields: Path = typer.Option(
        ...,
        "--fields",
        "-f",
        help="JSON object: field name -> type",
    ),
    extract_output: Optional[Path] = typer.Option(
        None,
        "--extract-output",
        help="Optional path to save intermediate extracted JSON",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output filled PDF path",
    ),
) -> None:
    """Extract with Ollama, then fill the PDF in one step."""
    transcript_text = transcript_file.read_text(encoding="utf-8")
    field_types = _load_json(fields)
    if not isinstance(field_types, dict):
        typer.echo("--fields JSON must be an object", err=True)
        raise typer.Exit(1)

    llm = LLM(transcript_text=transcript_text, target_fields=field_types, json={})
    llm.main_loop()
    data = llm.get_data()
    if extract_output:
        extract_output.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        typer.echo(f"Wrote intermediate JSON to {extract_output}", err=True)

    llm2 = LLM(transcript_text="", target_fields=field_types, json=data)
    filler = Filler()
    out = filler.fill_form(
        str(pdf_template),
        llm2,
        skip_extraction=True,
        output_pdf=str(output) if output else None,
    )
    typer.echo(out)


@app.command("version")
def version_cmd() -> None:
    """Print FireForm CLI version."""
    try:
        v = importlib.metadata.version("fireform")
    except importlib.metadata.PackageNotFoundError:
        v = "0.1.0 (not installed as package)"
    typer.echo(f"fireform {v}")
    typer.echo(f"Python {sys.version.split()[0]}")


@app.command("doctor")
def doctor_cmd() -> None:
    """Check Ollama, database, and core imports."""
    problems: list[str] = []

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        r = requests.get(f"{ollama_host}/api/tags", timeout=5)
        if r.status_code != 200:
            problems.append(f"Ollama at {ollama_host} returned HTTP {r.status_code}")
        else:
            typer.echo(f"Ollama OK ({ollama_host})")
    except requests.RequestException as e:
        problems.append(f"Ollama unreachable at {ollama_host}: {e}")

    try:
        import pdfrw  # noqa: F401

        typer.echo("pdfrw import OK")
    except ImportError as e:
        problems.append(f"pdfrw: {e}")

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        typer.echo("Database engine OK")
    except Exception as e:
        problems.append(f"Database: {e}")

    if problems:
        typer.echo("Issues:", err=True)
        for p in problems:
            typer.echo(f"  - {p}", err=True)
        raise typer.Exit(1)
    typer.echo("All checks passed.")


@template_app.command("list")
def template_list() -> None:
    """List templates in the local SQLite database."""
    try:
        with Session(engine) as session:
            rows = list_templates(session)
    except OperationalError as e:
        typer.echo(
            "Database not ready (missing tables). Run: python -m api.db.init_db",
            err=True,
        )
        raise typer.Exit(1) from e
    if not rows:
        typer.echo("(no templates)")
        return
    for t in rows:
        tid = t.id if t.id is not None else "?"
        typer.echo(f"{tid}\t{t.name}\t{t.pdf_path}")


@template_app.command("show")
def template_show(
    template_id: int = typer.Argument(..., help="Template primary key"),
) -> None:
    """Show one template as JSON."""
    try:
        with Session(engine) as session:
            row = get_template(session, template_id)
    except OperationalError as e:
        typer.echo(
            "Database not ready (missing tables). Run: python -m api.db.init_db",
            err=True,
        )
        raise typer.Exit(1) from e
    if row is None:
        typer.echo(f"Template id {template_id} not found.", err=True)
        raise typer.Exit(1)
    typer.echo(
        json.dumps(
            {
                "id": row.id,
                "name": row.name,
                "pdf_path": row.pdf_path,
                "fields": row.fields,
            },
            indent=2,
            default=str,
        )
    )


@template_app.command("create")
def template_create(
    pdf_path: Path = typer.Argument(..., exists=True, readable=True, help="Source PDF to prepare as template"),
) -> None:
    """Create an editable *_template.pdf next to the source (via commonforms)."""
    fm = FileManipulator()
    out = fm.create_template(str(pdf_path))
    typer.echo(out)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
