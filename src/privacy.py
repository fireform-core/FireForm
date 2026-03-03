import re
import uuid
import json

class PrivacyManager:
    def __init__(self):
        self._pii_map = {}
        # Simple regex for emails and phone numbers
        self.patterns = {
            "EMAIL": r'[\w\.-]+@[\w\.-]+\.\w+',
            "PHONE": r'\b(?:\+?\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b'
        }

    def tokenize(self, text: str) -> str:
        tokenized_text = text
        for label, pattern in self.patterns.items():
            matches = re.findall(pattern, tokenized_text)
            for match in matches:
                token = f"TOKEN_{label}_{uuid.uuid4().hex[:6].upper()}"
                self._pii_map[token] = match
                tokenized_text = tokenized_text.replace(match, token)
        return tokenized_text

    def detokenize(self, tokenized_data: dict) -> dict:
        # Convert dict to string, replace tokens, convert back to dict
        dumped = json.dumps(tokenized_data)
        for token, original_value in self._pii_map.items():
            dumped = dumped.replace(token, original_value)
        return json.loads(dumped)