import json
from pathlib import Path

import pytest

from json_manager import JsonManager


def test_load_json_raises_ioerror_for_corrupted_json(tmp_path: Path):
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{bad json", encoding="utf-8")

    with pytest.raises(IOError, match="is corrupted"):
        JsonManager().load_json(str(bad_json))


def test_load_json_returns_data_for_valid_json(tmp_path: Path):
    payload = {"name": "fireform", "ok": True}
    good_json = tmp_path / "good.json"
    good_json.write_text(json.dumps(payload), encoding="utf-8")

    data = JsonManager().load_json(str(good_json))
    assert data == payload