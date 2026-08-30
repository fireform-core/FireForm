"""Generate Pydantic models for the incident contract.

The incident contract (contracts/schemas/incident-contract.yaml) is the single
source of truth for every downstream form. This script turns it into typed
Pydantic v2 models so the extraction worker, validation, and correction paths
get typed access without anyone hand-writing (and then drifting) the models.

What it does:

1. The contract file is a flat map of named schemas, not a JSON Schema on its
   own, so we wrap every entry under `$defs` with a root `$ref` to
   IncidentContract and rewrite the internal `#/X` refs to `#/$defs/X`.
2. datamodel-code-generator turns that into Pydantic v2 models.
3. Enums the contract shares through contracts/schemas/enums.yaml already exist
   in app/api/schemas/enums.py. We drop the generated copies and import the
   existing ones instead, so there is one definition per enum. If a shared enum
   has drifted from enums.py, generation fails loudly and tells you to sync it.

Run it with `make generate-contract-models` whenever the contract changes.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "contracts" / "schemas" / "incident-contract.yaml"
ENUMS_YAML = REPO_ROOT / "contracts" / "schemas" / "enums.yaml"
ENUMS_PY = REPO_ROOT / "app" / "api" / "schemas" / "enums.py"
OUTPUT = REPO_ROOT / "app" / "api" / "schemas" / "incident_contract.py"
ENUMS_IMPORT = "app.api.schemas.enums"
ROOT_MODEL = "IncidentContract"

HEADER = """# This file is generated from contracts/schemas/incident-contract.yaml.
# DO NOT EDIT BY HAND. Run `make generate-contract-models` to regenerate.
"""


def shared_enum_names() -> set[str]:
    """Enum names the contract pulls in from enums.yaml (the deliberate shared
    set, so a field's inline enum that happens to share a name is left alone)."""
    text = CONTRACT.read_text()
    names = set()
    for line in text.splitlines():
        marker = "../schemas/enums.yaml#/"
        if marker in line:
            names.add(line.split(marker, 1)[1].strip().strip('"').strip("'"))
    return names


def enum_members_from_py() -> dict[str, list[str]]:
    """Read app/api/schemas/enums.py without importing it (no side effects)."""
    tree = ast.parse(ENUMS_PY.read_text())
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(isinstance(b, ast.Name) and b.id == "Enum" for b in node.bases):
            continue
        out[node.name] = [
            stmt.value.value
            for stmt in node.body
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
        ]
    return out


def enum_members_from_yaml() -> dict[str, list[str]]:
    data = yaml.safe_load(ENUMS_YAML.read_text())
    return {
        name: spec["enum"]
        for name, spec in data.items()
        if isinstance(spec, dict) and "enum" in spec
    }


def build_wrapped(dest: Path) -> None:
    """Wrap the flat contract in a JSON Schema envelope codegen can consume."""
    doc = yaml.safe_load(CONTRACT.read_text())

    def rewrite(obj):
        if isinstance(obj, dict):
            return {
                k: (
                    "#/$defs/" + v[2:]
                    if k == "$ref" and isinstance(v, str) and v.startswith("#/")
                    else rewrite(v)
                )
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [rewrite(i) for i in obj]
        return obj

    wrapped = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": ROOT_MODEL,
        "$ref": f"#/$defs/{ROOT_MODEL}",
        "$defs": rewrite(doc),
    }
    dest.write_text(yaml.safe_dump(wrapped, sort_keys=False))


def run_codegen(wrapped: Path, out: Path) -> None:
    subprocess.run(
        [
            "datamodel-codegen",
            "--input", str(wrapped),
            "--input-file-type", "jsonschema",
            "--output", str(out),
            "--output-model-type", "pydantic_v2.BaseModel",
            "--force-optional",
            "--use-schema-description",
            "--use-field-description",
            "--use-annotated",
            "--field-constraints",
            "--use-standard-collections",
            "--use-double-quotes",
            "--disable-timestamp",
            "--target-python-version", "3.11",
        ],
        check=True,
        cwd=REPO_ROOT,
    )


def strip_shared_enums(source: str, shared: set[str]) -> str:
    """Remove generated copies of the shared enums and import them instead.

    A shared enum is only removed when enums.py defines it with the exact same
    members; a mismatch means enums.py drifted from the contract, so we stop and
    say so rather than silently dropping members.
    """
    py_enums = enum_members_from_py()
    yaml_enums = enum_members_from_yaml()

    tree = ast.parse(source)
    drop_ranges: list[tuple[int, int]] = []
    reused: list[str] = []
    last_import_line = 0

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_import_line = max(last_import_line, node.end_lineno)
            continue
        if not isinstance(node, ast.ClassDef) or node.name not in shared:
            continue
        is_enum = any(isinstance(b, ast.Name) and b.id == "Enum" for b in node.bases)
        if not is_enum:
            continue
        expected = yaml_enums.get(node.name)
        if node.name not in py_enums or py_enums[node.name] != expected:
            sys.exit(
                f"Shared enum {node.name} in enums.py does not match the "
                f"contract. Sync app/api/schemas/enums.py to enums.yaml "
                f"({expected}) and re-run."
            )
        drop_ranges.append((node.lineno, node.end_lineno))
        reused.append(node.name)

    lines = source.splitlines()
    drop = {n for start, end in drop_ranges for n in range(start, end + 1)}
    kept = [line for i, line in enumerate(lines, start=1) if i not in drop]

    if reused:
        names = ", ".join(sorted(reused))
        import_line = f"from {ENUMS_IMPORT} import {names}"
        insert_at = sum(
            1 for i, _ in enumerate(lines, start=1) if i <= last_import_line and i not in drop
        )
        kept.insert(insert_at, import_line)

    return "\n".join(kept) + "\n"


# Types a contract field can share a name with. A field called `date` binds
# `date = None` in its class body, which shadows the imported type and leaves
# pydantic resolving the annotation to NoneType, so the field silently rejects
# every value. Importing these under a distinct name removes the collision.
SHADOWABLE_TYPES = {"date": "date_type", "time": "time_type"}


def alias_shadowed_types(source: str) -> str:
    """Import date and time under names no contract field can shadow."""
    imported = ", ".join(f"{name} as {alias}" for name, alias in SHADOWABLE_TYPES.items())
    out = source.replace("from datetime import date, time", f"from datetime import {imported}", 1)
    for name, alias in SHADOWABLE_TYPES.items():
        out = out.replace(f"Optional[{name}]", f"Optional[{alias}]")
    return out


def main() -> None:
    shared = shared_enum_names()
    with tempfile.TemporaryDirectory() as tmp:
        # Written next to enums.yaml so the "../schemas/enums.yaml" ref resolves.
        wrapped = CONTRACT.parent / ".contract.wrapped.yaml"
        raw = Path(tmp) / "models.py"
        try:
            build_wrapped(wrapped)
            run_codegen(wrapped, raw)
        finally:
            wrapped.unlink(missing_ok=True)
        body = alias_shadowed_types(strip_shared_enums(raw.read_text(), shared))

    # Drop codegen's own header; it names the temporary wrapped file.
    body = "\n".join(
        line
        for line in body.splitlines()
        if not line.startswith(("# generated by datamodel-codegen", "#   filename:"))
    ).lstrip("\n")

    OUTPUT.write_text(HEADER + "\n" + body + "\n")
    _ruff("check", "--fix", str(OUTPUT))
    _ruff("format", str(OUTPUT))
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)} (reused shared enums from enums.py).")


def _ruff(*args: str) -> None:
    """Tidy the output if ruff is available; skip quietly if it is not."""
    ruff = shutil.which("ruff")
    cmd = [ruff, *args] if ruff else [sys.executable, "-m", "ruff", *args]
    try:
        subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    main()
