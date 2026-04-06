import re

_PDF_ESCAPE_RE = re.compile(r'\\(\d{1,3}|[nrtbf()\\])')
_NAMED_ESCAPES = {
    'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
    '(': '(', ')': ')', '\\': '\\',
}


def decode_pdf_name(raw: str) -> str:
    """Decode all PDF literal-string escape sequences (ISO 32000 §7.3.4.2)."""
    def _replace(m: re.Match) -> str:
        s = m.group(1)
        if s[0].isdigit():
            return chr(int(s, 8))
        return _NAMED_ESCAPES.get(s, s)
    return _PDF_ESCAPE_RE.sub(_replace, raw)
