import builtins
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _blocking_import(original_import):
    def _imp(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "commonforms" or name.startswith("commonforms."):
            raise ImportError("simulated: commonforms unavailable")
        return original_import(name, globals, locals, fromlist, level)

    return _imp


def _commonforms_module_keys():
    return [k for k in list(sys.modules) if k == "commonforms" or k.startswith("commonforms.")]


def test_import_api_main_without_commonforms():
    root = Path(__file__).resolve().parents[1]
    code = r"""
import builtins
_real = builtins.__import__

def _imp(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "commonforms" or name.startswith("commonforms."):
        raise ImportError("simulated: commonforms unavailable")
    return _real(name, globals, locals, fromlist, level)

builtins.__import__ = _imp
import api.main
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr!r} stdout={proc.stdout!r}"


def test_create_template_raises_when_commonforms_missing(monkeypatch):
    original_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", _blocking_import(original_import))
    cf_keys = _commonforms_module_keys()
    saved_cf = {k: sys.modules.pop(k) for k in cf_keys if k in sys.modules}
    try:
        from src.file_manipulator import FileManipulator

        with pytest.raises(RuntimeError) as exc_info:
            FileManipulator().create_template("dummy.pdf")
        assert "commonforms" in str(exc_info.value)
    finally:
        sys.modules.update(saved_cf)
