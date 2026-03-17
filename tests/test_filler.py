import pytest
from unittest.mock import MagicMock
from pdfrw import PdfName
from src.filler import _resolve_checkbox_value, _resolve_radio_kid, _get_field_type


class TestResolveCheckboxValue:

    def _make_annot(self, ap_keys=None):
        annot = MagicMock()
        if ap_keys:
            annot.AP.N.keys.return_value = [f"/{k}" for k in ap_keys]
        else:
            annot.AP = None
        return annot

    def test_yes_string_returns_pdf_yes(self):
        annot = self._make_annot(["Yes", "Off"])
        assert str(_resolve_checkbox_value("yes", annot)) == "/Yes"

    def test_true_string_returns_checked(self):
        annot = self._make_annot(["Yes", "Off"])
        assert str(_resolve_checkbox_value("true", annot)) != "/Off"

    def test_no_string_returns_off(self):
        annot = self._make_annot(["Yes", "Off"])
        assert str(_resolve_checkbox_value("no", annot)) == "/Off"

    def test_false_string_returns_off(self):
        annot = self._make_annot()
        assert str(_resolve_checkbox_value("false", annot)) == "/Off"

    def test_empty_string_returns_off(self):
        annot = self._make_annot()
        assert str(_resolve_checkbox_value("", annot)) == "/Off"

    def test_no_ap_falls_back_to_yes(self):
        annot = self._make_annot()
        assert str(_resolve_checkbox_value("yes", annot)) == "/Yes"

    def test_custom_on_value_from_ap(self):
        annot = self._make_annot(["On", "Off"])
        assert str(_resolve_checkbox_value("yes", annot)) == "/On"

    def test_x_means_checked(self):
        annot = self._make_annot(["Yes", "Off"])
        assert str(_resolve_checkbox_value("x", annot)) != "/Off"

    def test_none_value_returns_off(self):
        annot = self._make_annot()
        assert str(_resolve_checkbox_value("none", annot)) == "/Off"


class TestResolveRadioKid:

    def _make_annot(self, ap_keys=None, opt_list=None):
        annot = MagicMock()
        if ap_keys:
            annot.AP.N.keys.return_value = [f"/{k}" for k in ap_keys]
        else:
            annot.AP = None
        if opt_list:
            annot.Parent.Opt = [f"({o})" for o in opt_list]
        else:
            annot.Parent = None
        return annot

    def test_selected_returns_option_value(self):
        """kid_index=0, raw='male', opt=['Male','Female'] → /Male"""
        annot = self._make_annot(ap_keys=["Male", "Off"], opt_list=["Male", "Female"])
        result = _resolve_radio_kid("male", 0, annot)
        assert str(result) == "/Male"

    def test_unselected_returns_off(self):
        """kid_index=0 is Male but raw='female' → /Off"""
        annot = self._make_annot(ap_keys=["Male", "Off"], opt_list=["Male", "Female"])
        result = _resolve_radio_kid("female", 0, annot)
        assert str(result) == "/Off"

    def test_no_parent_returns_off(self):
        """No parent opt list → cannot determine selection → /Off"""
        annot = self._make_annot()
        result = _resolve_radio_kid("yes", 0, annot)
        assert str(result) == "/Off"


class TestGetFieldType:

    def _make_annot(self, ft, ff=0):
        annot = MagicMock()
        annot.FT = f"/{ft}"
        annot.Ff = str(ff)
        return annot

    def test_text_field(self):
        assert _get_field_type(self._make_annot("Tx")) == "text"

    def test_checkbox_field(self):
        assert _get_field_type(self._make_annot("Btn", ff=0)) == "checkbox"

    def test_radio_field(self):
        assert _get_field_type(self._make_annot("Btn", ff=1 << 15)) == "radio"

    def test_unknown_field_type(self):
        assert _get_field_type(self._make_annot("Sig")) == "other"

    def test_no_ft_returns_other(self):
        annot = MagicMock()
        annot.FT = None
        assert _get_field_type(annot) == "other"