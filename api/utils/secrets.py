"""
Secrets sanitization utilities for logging and error handling.
Prevents accidental exposure of sensitive credentials in logs.
"""

import re
from typing import Any


# Patterns to detect and redact secrets
REDACT_PATTERNS = [
    # API keys
    (r'(api[_-]?key["\s:=]+)([a-zA-Z0-9\-_]{20,})', r'\1***REDACTED***'),
    # Passwords
    (r'(password["\s:=]+)([^\s"]+)', r'\1***REDACTED***'),
    # Tokens
    (r'(token["\s:=]+)([a-zA-Z0-9\-_.]{20,})', r'\1***REDACTED***'),
    # Database URLs with credentials
    (r'(postgresql://|mysql://|mongodb://)([^:]+):([^@]+)@', r'\1\2:***REDACTED***@'),
    # Bearer tokens
    (r'(Bearer\s+)([a-zA-Z0-9\-_.]+)', r'\1***REDACTED***'),
    # Secret keys
    (r'(secret[_-]?key["\s:=]+)([a-zA-Z0-9\-_]{20,})', r'\1***REDACTED***'),
]


def sanitize_string(text: str) -> str:
    """
    Sanitize a string by redacting known secret patterns.
    
    Args:
        text: String that may contain secrets
        
    Returns:
        Sanitized string with secrets redacted
        
    Example:
        >>> sanitize_string("api_key=sk_test_123456789")
        'api_key=***REDACTED***'
    """
    if not isinstance(text, str):
        return text
    
    sanitized = text
    for pattern, replacement in REDACT_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    
    return sanitized


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively sanitize a dictionary by redacting secret values.
    
    Args:
        data: Dictionary that may contain secrets
        
    Returns:
        Sanitized dictionary with secrets redacted
        
    Example:
        >>> sanitize_dict({"api_key": "secret123", "user": "admin"})
        {'api_key': '***REDACTED***', 'user': 'admin'}
    """
    if not isinstance(data, dict):
        return data
    
    # Keys that should always be redacted
    SENSITIVE_KEYS = {
        'password', 'passwd', 'pwd',
        'secret', 'secret_key', 'api_key', 'apikey',
        'token', 'access_token', 'refresh_token',
        'private_key', 'credentials', 'auth'
    }
    
    sanitized = {}
    for key, value in data.items():
        # Check if key is sensitive
        if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
            sanitized[key] = '***REDACTED***'
        # Recursively sanitize nested dicts
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        # Sanitize string values
        elif isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        # Keep other values as-is
        else:
            sanitized[key] = value
    
    return sanitized


def sanitize_log_message(message: str, context: dict[str, Any] | None = None) -> tuple[str, dict[str, Any] | None]:
    """
    Sanitize both log message and context dict.
    
    Args:
        message: Log message string
        context: Optional context dictionary
        
    Returns:
        Tuple of (sanitized_message, sanitized_context)
    """
    sanitized_message = sanitize_string(message)
    sanitized_context = sanitize_dict(context) if context else None
    
    return sanitized_message, sanitized_context