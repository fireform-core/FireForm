import re


MISSING_VALUE_SENTINEL = "__MISSING__"


class ExtractionQualityProcessor:
    """Normalize and merge extracted values from noisy conversational outputs."""

    def __init__(self, missing_sentinel=MISSING_VALUE_SENTINEL):
        self.missing_sentinel = missing_sentinel
        self.duplicate_fields = set()
        self.ambiguous_fields = set()
        self.plural_normalized_fields = set()
        self.missing_fields = set()

    def process(self, field, raw_value, existing_value=None):
        normalized_value, was_plural, is_ambiguous = self._normalize_value(raw_value)

        if was_plural:
            self.plural_normalized_fields.add(field)
        if is_ambiguous:
            self.ambiguous_fields.add(field)

        if existing_value is None:
            merged_value = normalized_value
            had_duplicate = False
        else:
            merged_value, had_duplicate = self._merge_values(existing_value, normalized_value)

        if had_duplicate:
            self.duplicate_fields.add(field)

        if self._is_missing(merged_value):
            self.missing_fields.add(field)
        else:
            # Ensure the field is not reported as missing if the final merged value is present
            self.missing_fields.discard(field)

        return merged_value

    def build_report(self):
        return {
            "missing_sentinel": self.missing_sentinel,
            "duplicate_fields": sorted(self.duplicate_fields),
            "ambiguous_fields": sorted(self.ambiguous_fields),
            "plural_normalized_fields": sorted(self.plural_normalized_fields),
            "missing_fields": sorted(self.missing_fields),
        }

    def _normalize_value(self, raw_value):
        if raw_value is None:
            return self.missing_sentinel, False, False

        value = str(raw_value).strip().replace('"', "")

        if value == "" or value == "-1":
            return self.missing_sentinel, False, False

        if ";" in value:
            plural_values = self._normalize_plural_values(value)
            if not plural_values:
                return self.missing_sentinel, True, False
            is_ambiguous = any(self._is_ambiguous_token(item) for item in plural_values)
            return plural_values, True, is_ambiguous

        return value, False, self._is_ambiguous_token(value)

    def _normalize_plural_values(self, raw_plural_value):
        values = [part.strip() for part in raw_plural_value.split(";")]
        values = [value for value in values if value and value != "-1"]
        return self._unique_ordered(values)

    def _merge_values(self, existing_value, new_value):
        if self._is_missing(new_value):
            return existing_value, False

        if self._is_missing(existing_value):
            return new_value, False

        existing_values = existing_value if isinstance(existing_value, list) else [existing_value]
        new_values = new_value if isinstance(new_value, list) else [new_value]

        merged = list(existing_values)
        had_duplicate = False

        for value in new_values:
            if value in merged:
                had_duplicate = True
                continue
            merged.append(value)

        if len(merged) == 1:
            return merged[0], had_duplicate

        return merged, had_duplicate

    def _is_missing(self, value):
        return value == self.missing_sentinel

    def _is_ambiguous_token(self, token):
        token = token.strip().lower()
        return bool(re.search(r"\b(or|maybe|possibly|unclear|unknown)\b", token))

    def _unique_ordered(self, values):
        seen = set()
        out = []

        for value in values:
            if value in seen:
                continue
            seen.add(value)
            out.append(value)

        return out
