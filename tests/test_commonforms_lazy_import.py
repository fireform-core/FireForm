import importlib


def test_importing_api_main_does_not_eagerly_import_commonforms(monkeypatch):
    """Regression test for environments where commonforms (cv2/numpy) crashes.

    The FastAPI app should be importable without importing `commonforms`.
    Template creation should be the only place that tries to import it.
    """

    def _fail_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "commonforms":
            raise ImportError("commonforms should not be imported at app import time")
        return original_import(name, globals, locals, fromlist, level)

    original_import = __builtins__["__import__"]
    monkeypatch.setitem(__builtins__, "__import__", _fail_import)

    # Should not raise
    importlib.import_module("api.main")
