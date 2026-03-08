"""
Unit tests for the Translator module (Issue #107).

All tests mock away network calls so they run offline without any real
translate API or internet access.
"""

from unittest.mock import patch, MagicMock
import pytest
from src.translator import Translator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_google_translator_mock(translated_text: str):
    """Return a mock that mimics deep_translator.GoogleTranslator."""
    mock_instance = MagicMock()
    mock_instance.translate.return_value = translated_text
    mock_cls = MagicMock(return_value=mock_instance)
    return mock_cls


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTranslator:
    def test_french_input_translates_to_english(self):
        """French text should be translated to English and lang code returned."""
        french_text = "Le nom de l'employé est Jean Dupont."
        expected_english = "The employee's name is Jean Dupont."

        with patch("src.translator._detect_language", return_value="fr"):
            with patch(
                "deep_translator.GoogleTranslator",
                _make_google_translator_mock(expected_english),
            ):
                t = Translator()
                translated, lang = t.translate_to_english(french_text)

        assert translated == expected_english
        assert lang == "fr"

    def test_arabic_input_translates_to_english(self):
        """Arabic text should be translated to English and lang code returned."""
        arabic_text = "اسم الموظف هو محمد علي."
        expected_english = "The employee's name is Mohammed Ali."

        with patch("src.translator._detect_language", return_value="ar"):
            with patch(
                "deep_translator.GoogleTranslator",
                _make_google_translator_mock(expected_english),
            ):
                t = Translator()
                translated, lang = t.translate_to_english(arabic_text)

        assert translated == expected_english
        assert lang == "ar"

    def test_spanish_input_translates_to_english(self):
        """Spanish text should be translated to English and lang code returned."""
        spanish_text = "El nombre del empleado es Carlos García."
        expected_english = "The employee's name is Carlos García."

        with patch("src.translator._detect_language", return_value="es"):
            with patch(
                "deep_translator.GoogleTranslator",
                _make_google_translator_mock(expected_english),
            ):
                t = Translator()
                translated, lang = t.translate_to_english(spanish_text)

        assert translated == expected_english
        assert lang == "es"

    def test_english_input_passes_through_unchanged(self):
        """English text should be returned as-is without any translation call."""
        english_text = "The employee's name is John Doe."

        with patch("src.translator._detect_language", return_value="en"):
            # GoogleTranslator should NOT be called for English input
            with patch("deep_translator.GoogleTranslator") as mock_gt:
                t = Translator()
                translated, lang = t.translate_to_english(english_text)

        assert translated == english_text
        assert lang == "en"
        mock_gt.assert_not_called()

    def test_empty_string_returns_en(self):
        """Empty input should be returned unchanged with language 'en'."""
        t = Translator()
        translated, lang = t.translate_to_english("")
        assert translated == ""
        assert lang == "en"

    def test_translation_failure_falls_back_gracefully(self):
        """If the translation service raises, the original text is returned."""
        french_text = "Le nom de l'employé est Jean Dupont."

        with patch("src.translator._detect_language", return_value="fr"):
            with patch("deep_translator.GoogleTranslator", side_effect=Exception("Network error")):
                t = Translator()
                translated, lang = t.translate_to_english(french_text)

        # Falls back to original text
        assert translated == french_text
        assert lang == "fr"

    def test_detection_failure_defaults_to_english(self):
        """If language detection itself fails, the text is returned as-is."""
        english_text = "Hello world."

        # _detect_language raises → helper falls back to 'en'
        with patch("langdetect.detect", side_effect=Exception("detect failed")):
            t = Translator()
            translated, lang = t.translate_to_english(english_text)

        assert translated == english_text
        assert lang == "en"
