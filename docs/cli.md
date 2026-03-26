# FireForm CLI

The `fireform` command provides a unified interface for local development: LLM extraction (Ollama), PDF filling, template file creation, and (when the SQLite DB is initialized) template listing.

## Install

From the repository root (install full dependencies first, then the package in editable mode):

```bash
pip install -r requirements.txt
pip install -e .
```

The `pyproject.toml` lists a minimal dependency set so `pip install -e .` can succeed in constrained environments; the full project (tests, optional stacks) expects everything in `requirements.txt`.

Or run without installing the package:

```bash
python -m src.cli --help
```

Ensure `OLLAMA_HOST` is set if Ollama is not on `http://localhost:11434`.

Initialize the API database (for `template list` / `template show`):

```bash
python -m api.db.init_db
```

## Global options

Place **before** the subcommand:

| Option | Meaning |
|--------|---------|
| `--verbose` / `-v` | DEBUG/INFO logging (includes PDF filler validation logs) |
| `--quiet` / `-q` | Only warnings and errors |

Example:

```bash
python -m src.cli --verbose fill data.json template.pdf
```

## Commands

### `extract`

Run extraction on a transcript using Ollama. Requires a `--fields` JSON file: field names map to types (`string`, `number`, `email`, `date`), same shape as template `fields` in the API.

```bash
python -m src.cli extract transcript.txt --fields fields.json
python -m src.cli extract transcript.txt -f fields.json -o out.json
```

- `--output` / `-o`: also write JSON to a file (still prints to stdout unless `--stdout-only`).
- `--stdout-only`: print only to stdout (ignore `--output`).

### `fill`

Fill a PDF from a JSON object **without** calling Ollama. Values must match PDF field order (see `src/filler.py`).

```bash
python -m src.cli fill answers.json path/to/template.pdf
python -m src.cli fill answers.json template.pdf -f field_types.json -o filled.pdf
```

If `--fields` is omitted, every key in `answers.json` is treated as type `string`.

### `pipeline`

Extract then fill in one step.

```bash
python -m src.cli pipeline transcript.txt template.pdf --fields fields.json
python -m src.cli pipeline transcript.txt template.pdf -f fields.json --extract-output step.json -o out.pdf
```

### `version`

Print package and Python versions.

### `doctor`

Checks Ollama (`/api/tags`), `pdfrw` import, and database engine connectivity. Exits with code `1` if something critical fails.

### `template list`

List rows in the local `fireform.db` (id, name, pdf_path).

### `template show <id>`

Print one template as JSON.

### `template create <pdf_path>`

Run `commonforms` preparation and print the path to the generated `*_template.pdf`.

## Shell completion

Typer can install shell completion (see `python -m src.cli --help` for `--install-completion`).

## Examples

**fields.json** (types for extraction):

```json
{
  "Employee's name": "string",
  "Date": "date"
}
```

**answers.json** (for fill):

```json
{
  "Employee's name": "Jane Doe",
  "Date": "2025-01-15"
}
```
