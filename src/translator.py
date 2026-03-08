"""
Translator module for FireForm — Issue #107.

Detects the language of the input text and translates it to English
before the LLM processes the form fields.  This ensures the Master
Schema is always produced in English regardless of the responder's
native language.

Supported back-end: Google Translate (via deep-translator, no API key
required for short texts).
"""

from __future__ import annotations


def _detect_language(text: str) -> str:
    """Return the BCP-47 language code for *text* (e.g. 'fr', 'ar', 'en').

    Falls back to ``'en'`` if detection fails so that the pipeline can
    always continue.
    """
    try:
        from langdetect import detect, LangDetectException  # type: ignore

        return detect(text)
    except Exception:
        return "en"


class Translator:
    """Lightweight translation wrapper for the FireForm pipeline.

    Example usage::

        translator = Translator()
        english_text, lang_code = translator.translate_to_english(
            "Le nom de l'employé est Jean Dupont."
        )
        # english_text -> "The employee's name is Jean Dupont."
        # lang_code    -> "fr"
    """

    def translate_to_english(self, text: str) -> tuple[str, str]:
        """Translate *text* to English and return ``(translated_text, source_lang_code)``.

        If the detected language is already English (``"en"``), the
        original text is returned as-is without calling a translation
        service.

        Args:
            text: Raw input string (may be any language).

        Returns:
            A tuple of:
            - ``translated_text`` (str) – the English version of *text*.
            - ``source_lang`` (str) – BCP-47 code of the detected source
              language (e.g. ``"fr"``, ``"ar"``, ``"en"``).
        """
        if not text or not text.strip():
            return text, "en"

        source_lang = _detect_language(text)

        if source_lang == "en":
            return text, "en"

        try:
            from deep_translator import GoogleTranslator  # type: ignore

            translated = GoogleTranslator(
                source=source_lang, target="en"
            ).translate(text)
            return translated, source_lang
        except Exception as exc:
            # If translation fails (e.g. network issue), log a warning and
            # fall back to the original text so the pipeline is never blocked.
            print(
                f"[WARNING] Translation failed (source={source_lang}): {exc}. "
                "Falling back to original text."
            )
            return text, source_lang
