from pathlib import Path

from fastapi import HTTPException

from app.core.config import BASE_DIR, DEFAULT_TEMPLATE_DIR

PROJECT_ROOT = BASE_DIR


def _resolve_target_directory(directory: str) -> Path:
    dir_value = (directory or DEFAULT_TEMPLATE_DIR).strip()
    if not dir_value:
        raise HTTPException(status_code=400, detail="Directory is required.")

    candidate = Path(dir_value)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise HTTPException(status_code=400, detail="Directory must be inside the project.")

    return candidate


def _resolve_project_file(file_path: str) -> Path:
    raw_path = (file_path or "").strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="Path is required.")

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise HTTPException(status_code=400, detail="Path must be inside the project.")

    return candidate
