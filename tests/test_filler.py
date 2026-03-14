import pytest
from unittest.mock import MagicMock, patch
from pdfrw import PdfName
from src.filler import _resolve_checkbox_value, _resolve_radio_value, _get_field_type


# ── Checkbox value resolution ─────────────────────────────

class TestResolveCheckboxValue:

    def _make_annot(self, ap_keys=None):
        """Build a mock annotation with optional AP.N keys."""
        annot = MagicMock()
        if ap_keys:
            annot.AP.N.keys.return_value = [f"/{k}" for k in ap_keys]
        else:
            annot.AP = None
        return annot

    def test_yes_string_returns_pdf_yes(self):
        annot = self._make_annot(["Yes", "Off"])
        result = _resolve_checkbox_value("yes", annot)
        assert str(result) == "/Yes"

    def test_true_string_returns_checked(self):
        annot = self._make_annot(["Yes", "Off"])
        result = _resolve_checkbox_value("true", annot)
        assert str(result) != "/Off"

    def test_no_string_returns_off(self):
        annot = self._make_annot(["Yes", "Off"])
        result = _resolve_checkbox_value("no", annot)
        assert str(result) == "/Off"

    def test_false_string_returns_off(self):
        annot = self._make_annot()
        result = _resolve_checkbox_value("false", annot)
        assert str(result) == "/Off"

    def test_empty_string_returns_off(self):
        annot = self._make_annot()
        result = _resolve_checkbox_value("", annot)
        assert str(result) == "/Off"

    def test_no_ap_falls_back_to_yes(self):
        """When AP is missing, fallback to /Yes for checked state."""
        annot = self._make_annot()
        result = _resolve_checkbox_value("yes", annot)
        assert str(result) == "/Yes"

    def test_custom_on_value_from_ap(self):
        """PDF uses /On instead of /Yes — should read from AP."""
        annot = self._make_annot(["On", "Off"])
        result = _resolve_checkbox_value("yes", annot)
        assert str(result) == "/On"

    def test_x_means_checked(self):
        annot = self._make_annot(["Yes", "Off"])
        result = _resolve_checkbox_value("x", annot)
        assert str(result) != "/Off"

    def test_none_value_returns_off(self):
        annot = self._make_annot()
        result = _resolve_checkbox_value("none", annot)
        assert str(result) == "/Off"


# ── Radio button value resolution ────────────────────────

class TestResolveRadioValue:

    def _make_annot(self, ap_keys=None):
        annot = MagicMock()
        if ap_keys:
            annot.AP.N.keys.return_value = [f"/{k}" for k in ap_keys]
        else:
            annot.AP = None
        return annot

    def test_selected_returns_option_value(self):
        annot = self._make_annot(["Male", "Off"])
        result = _resolve_radio_value("yes", annot)
        assert str(result) == "/Male"

    def test_unselected_returns_off(self):
        annot = self._make_annot(["Male", "Off"])
        result = _resolve_radio_value("no", annot)
        assert str(result) == "/Off"

    def test_no_ap_falls_back_to_yes(self):
        annot = self._make_annot()
        result = _resolve_radio_value("yes", annot)
        assert str(result) == "/Yes"


# ── Field type detection ──────────────────────────────────

class TestGetFieldType:

    def _make_annot(self, ft, ff=0):
        annot = MagicMock()
        annot.FT = f"/{ft}"
        annot.Ff = str(ff)
        return annot

    def test_text_field(self):
        annot = self._make_annot("Tx")
        assert _get_field_type(annot) == "text"

    def test_checkbox_field(self):
        annot = self._make_annot("Btn", ff=0)
        assert _get_field_type(annot) == "checkbox"

    def test_radio_field(self):
        # Bit 16 (0-indexed 15) set = radio button
        annot = self._make_annot("Btn", ff=1 << 15)
        assert _get_field_type(annot) == "radio"

    def test_unknown_field_type(self):
        annot = self._make_annot("Sig")
        assert _get_field_type(annot) == "other"

    def test_no_ft_returns_other(self):
        annot = MagicMock()
        annot.FT = None
        assert _get_field_type(annot) == "other"