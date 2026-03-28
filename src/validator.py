"""
Incident Data Validation Module for FireForm.

This module provides comprehensive input-side validation for incident data,
ensuring data integrity at multiple stages of the pipeline:

1. Transcript Validation: Validates raw user input before LLM processing
2. Incident Data Validation: Validates extracted data before PDF generation
3. Template Field Validation: Validates template configuration

The validator catches incomplete or malformed data early to prevent downstream
failures and provides clear, actionable error messages.

Author: dhanasai2
Fixes: https://github.com/fireform-core/FireForm/issues/305
"""

from typing import Any, Callable, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import re


class ErrorSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"      # Blocks processing - must be fixed
    WARNING = "warning"  # Allows processing but logs concern


@dataclass
class ValidationError:
    """Represents a single validation error with full context."""
    field: str
    message: str
    error_type: str  # 'missing', 'empty', 'invalid_type', 'invalid_format', 'too_short'
    severity: ErrorSeverity = ErrorSeverity.ERROR
    value: Any = None  # The actual value that failed validation

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "field": self.field,
            "message": self.message,
            "error_type": self.error_type,
            "severity": self.severity.value,
            "value": self._safe_value_repr()
        }

    def _safe_value_repr(self) -> str:
        """Return a safe string representation of the value."""
        if self.value is None:
            return "null"
        val_str = str(self.value)
        return val_str[:100] + "..." if len(val_str) > 100 else val_str


@dataclass
class ValidationResult:
    """Contains the complete result of validation operation."""
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings)
        }

    def get_error_messages(self) -> list[str]:
        """Return list of error messages for simple display."""
        return [e.message for e in self.errors]

    def get_all_messages(self) -> list[str]:
        """Return all messages including warnings."""
        return [e.message for e in self.errors + self.warnings]

    def raise_if_invalid(self) -> None:
        """Raise ValidationException if validation failed."""
        if not self.is_valid:
            raise ValidationException(
                errors=self.errors,
                message=f"Validation failed with {len(self.errors)} error(s)"
            )


class ValidationException(Exception):
    """Exception raised when validation fails."""

    def __init__(self, errors: list[ValidationError], message: str = "Validation failed"):
        self.errors = errors
        self.message = message
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON/API response."""
        return {
            "message": self.message,
            "errors": [e.to_dict() for e in self.errors]
        }

    def get_error_messages(self) -> list[str]:
        """Return list of error messages."""
        return [e.message for e in self.errors]


class TranscriptValidator:
    """
    Validates raw transcript/user input before LLM processing.

    This ensures the input is suitable for processing and catches
    obvious issues before expensive LLM calls.
    """

    # Minimum transcript length for meaningful extraction
    MIN_TRANSCRIPT_LENGTH = 10

    # Maximum transcript length to prevent abuse
    MAX_TRANSCRIPT_LENGTH = 50000

    # Keywords that suggest valid incident content
    INCIDENT_KEYWORDS = [
        "fire", "accident", "emergency", "incident", "respond", "call",
        "arrived", "scene", "victim", "injured", "damage", "rescue",
        "ambulance", "police", "report", "dispatch", "location", "address"
    ]

    def validate(self, transcript: Any) -> ValidationResult:
        """
        Validate transcript input.

        Args:
            transcript: The raw transcript text to validate.

        Returns:
            ValidationResult with validation status and any errors/warnings.
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # Type validation
        if transcript is None:
            errors.append(ValidationError(
                field="transcript",
                message="Transcript cannot be None",
                error_type="invalid_type",
                value=transcript
            ))
            return ValidationResult(is_valid=False, errors=errors)

        if not isinstance(transcript, str):
            errors.append(ValidationError(
                field="transcript",
                message=f"Transcript must be a string, got {type(transcript).__name__}",
                error_type="invalid_type",
                value=transcript
            ))
            return ValidationResult(is_valid=False, errors=errors)

        # Empty/whitespace validation
        if not transcript.strip():
            errors.append(ValidationError(
                field="transcript",
                message="Transcript cannot be empty or contain only whitespace",
                error_type="empty",
                value=repr(transcript)
            ))
            return ValidationResult(is_valid=False, errors=errors)

        # Length validation
        clean_transcript = transcript.strip()
        if len(clean_transcript) < self.MIN_TRANSCRIPT_LENGTH:
            errors.append(ValidationError(
                field="transcript",
                message=f"Transcript too short ({len(clean_transcript)} chars). "
                        f"Minimum {self.MIN_TRANSCRIPT_LENGTH} characters required for meaningful extraction.",
                error_type="too_short",
                value=clean_transcript
            ))

        if len(clean_transcript) > self.MAX_TRANSCRIPT_LENGTH:
            errors.append(ValidationError(
                field="transcript",
                message=f"Transcript too long ({len(clean_transcript)} chars). "
                        f"Maximum {self.MAX_TRANSCRIPT_LENGTH} characters allowed.",
                error_type="too_long",
                value=f"[{len(clean_transcript)} characters]"
            ))

        # Check for incident-related content (warning only)
        if not self._contains_incident_keywords(clean_transcript):
            warnings.append(ValidationError(
                field="transcript",
                message="Transcript may not contain incident-related content. "
                        "Extraction accuracy may be reduced.",
                error_type="content_warning",
                severity=ErrorSeverity.WARNING,
                value=clean_transcript[:100]
            ))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def _contains_incident_keywords(self, text: str) -> bool:
        """Check if text contains any incident-related keywords."""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.INCIDENT_KEYWORDS)


class IncidentValidator:
    """
    Validates incident data extracted from LLM before PDF generation.

    This validator ensures that required fields are present and properly formatted
    before the data is used to fill PDF forms. It's designed to be configurable
    for different agency requirements.
    """

    # Default required fields for incident reports
    DEFAULT_REQUIRED_FIELDS = [
        "incident_type",
        "location",
        "time",
        "date",
        "reporting_officer"
    ]

    # Fields that commonly have specific format requirements
    FORMAT_PATTERNS = {
        "date": r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$",
        "time": r"^\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)?$",
        "phone": r"^\+?[\d\s\-\(\)]{7,}$",
        "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    }

    def __init__(self, required_fields: list[str] | None = None):
        """
        Initialize the validator with configurable required fields.

        Args:
            required_fields: List of field names that must be present and non-empty.
                           If None, uses DEFAULT_REQUIRED_FIELDS.
        """
        self.required_fields = required_fields or self.DEFAULT_REQUIRED_FIELDS

    def validate(self, incident_data: Any) -> ValidationResult:
        """
        Main validation entry point. Validates incident data dictionary.

        Args:
            incident_data: Dictionary of extracted incident data from LLM.

        Returns:
            ValidationResult with is_valid flag and list of any errors found.
        """
        errors: list[ValidationError] = []

        # Type validation - must be a dictionary
        if not isinstance(incident_data, dict):
            errors.append(ValidationError(
                field="incident_data",
                message=f"Incident data must be a dictionary, got {type(incident_data).__name__}",
                error_type="invalid_type"
            ))
            return ValidationResult(is_valid=False, errors=errors)

        # Check for empty dictionary
        if not incident_data:
            errors.append(ValidationError(
                field="incident_data",
                message="Incident data cannot be empty",
                error_type="empty"
            ))
            return ValidationResult(is_valid=False, errors=errors)

        # Validate required fields
        errors.extend(self._validate_required_fields(incident_data))

        # Validate field values are not empty/whitespace
        errors.extend(self._validate_field_values(incident_data))

        # Validate field formats where applicable
        errors.extend(self._validate_field_formats(incident_data))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors
        )

    def _validate_required_fields(self, data: dict) -> list[ValidationError]:
        """Check that all required fields are present in the data."""
        errors = []

        for field_name in self.required_fields:
            if field_name not in data:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Required field '{field_name}' is missing",
                    error_type="missing"
                ))

        return errors

    def _validate_field_values(self, data: dict) -> list[ValidationError]:
        """Check that field values are not empty, None, or whitespace-only."""
        errors = []

        for field_name, value in data.items():
            # Check for None values
            if value is None:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Field '{field_name}' has null value",
                    error_type="empty"
                ))
                continue

            # Check for LLM's "not found" indicator
            if value == "-1":
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Field '{field_name}' was not found in the input text",
                    error_type="empty"
                ))
                continue

            # Check for empty strings or whitespace-only strings
            if isinstance(value, str):
                if not value.strip():
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Field '{field_name}' is empty or contains only whitespace",
                        error_type="empty"
                    ))

            # Check for empty lists
            elif isinstance(value, list):
                if len(value) == 0:
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Field '{field_name}' is an empty list",
                        error_type="empty"
                    ))
                # Check for lists containing only empty/whitespace strings
                elif all(isinstance(v, str) and not v.strip() for v in value):
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Field '{field_name}' contains only empty values",
                        error_type="empty"
                    ))

        return errors

    def _validate_field_formats(self, data: dict) -> list[ValidationError]:
        """
        Validate field formats for known field types.

        Note: This is optional validation - format errors are warnings,
        not hard failures, since LLM output can vary.
        """
        import re
        errors = []

        for field_name, pattern in self.FORMAT_PATTERNS.items():
            if field_name in data:
                value = data[field_name]
                if isinstance(value, str) and value.strip() and value != "-1":
                    if not re.match(pattern, value.strip()):
                        # Log warning but don't fail - LLM output format varies
                        print(f"[VALIDATION WARNING] Field '{field_name}' has unexpected format: {value}")

        return errors


def validate_incident(incident_data: Any, required_fields: list[str] | None = None) -> list[str]:
    """
    Convenience function to validate incident data.

    This is the primary interface for the validation module, matching
    the specification in Issue #305.

    Args:
        incident_data: Dictionary of extracted incident data.
        required_fields: Optional list of required field names.

    Returns:
        Empty list if valid, list of error messages if invalid.

    Example:
        >>> errors = validate_incident({"incident_type": "Fire", "location": "123 Main St"})
        >>> if errors:
        ...     print("Validation failed:", errors)
    """
    validator = IncidentValidator(required_fields=required_fields)
    result = validator.validate(incident_data)
    return result.get_error_messages()


def validate_incident_strict(incident_data: Any, required_fields: list[str] | None = None) -> ValidationResult:
    """
    Strict validation that returns full ValidationResult with error details.

    Use this when you need detailed error information including field names
    and error types for programmatic handling.

    Args:
        incident_data: Dictionary of extracted incident data.
        required_fields: Optional list of required field names.

    Returns:
        ValidationResult object with is_valid flag and detailed errors.
    """
    validator = IncidentValidator(required_fields=required_fields)
    return validator.validate(incident_data)


def validate_transcript(transcript: Any) -> list[str]:
    """
    Validate raw transcript input before LLM processing.

    Args:
        transcript: The raw transcript text to validate.

    Returns:
        Empty list if valid, list of error messages if invalid.

    Example:
        >>> errors = validate_transcript("Fire at 123 Main St, 2 victims")
        >>> if errors:
        ...     print("Invalid transcript:", errors)
    """
    validator = TranscriptValidator()
    result = validator.validate(transcript)
    return result.get_error_messages()


def validate_transcript_strict(transcript: Any) -> ValidationResult:
    """
    Strict transcript validation returning full ValidationResult.

    Args:
        transcript: The raw transcript text to validate.

    Returns:
        ValidationResult with is_valid flag, errors, and warnings.
    """
    validator = TranscriptValidator()
    return validator.validate(transcript)


def validate_template_fields(fields: Any) -> list[str]:
    """
    Validate template field configuration.

    Args:
        fields: Template fields (dict or list) to validate.

    Returns:
        Empty list if valid, list of error messages if invalid.
    """
    errors = []

    if fields is None:
        errors.append("Template fields cannot be None")
    elif not isinstance(fields, (dict, list)):
        errors.append(f"Template fields must be dict or list, got {type(fields).__name__}")
    elif len(fields) == 0:
        errors.append("Template fields cannot be empty")
    elif isinstance(fields, dict):
        # Validate each field has a valid name
        for key in fields.keys():
            if not isinstance(key, str) or not key.strip():
                errors.append(f"Field name must be a non-empty string, got: {repr(key)}")

    return errors


def validate_pdf_path(pdf_path: Any) -> list[str]:
    """
    Validate PDF file path.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Empty list if valid, list of error messages if invalid.
    """
    import os
    errors = []

    if pdf_path is None:
        errors.append("PDF path cannot be None")
    elif not isinstance(pdf_path, str):
        errors.append(f"PDF path must be a string, got {type(pdf_path).__name__}")
    elif not pdf_path.strip():
        errors.append("PDF path cannot be empty")
    elif not pdf_path.lower().endswith('.pdf'):
        errors.append("PDF path must end with .pdf extension")
    elif not os.path.exists(pdf_path):
        errors.append(f"PDF file not found: {pdf_path}")

    return errors


def validate_all_inputs(
    transcript: str,
    fields: dict,
    pdf_path: str
) -> ValidationResult:
    """
    Validate all inputs before starting the form filling pipeline.

    This is a convenience function that validates transcript, fields, and
    PDF path in one call, returning a combined result.

    Args:
        transcript: The raw transcript/user input text.
        fields: Template fields configuration.
        pdf_path: Path to the PDF template file.

    Returns:
        ValidationResult with combined errors from all validations.
    """
    all_errors: list[ValidationError] = []
    all_warnings: list[ValidationError] = []

    # Validate transcript
    transcript_result = validate_transcript_strict(transcript)
    all_errors.extend(transcript_result.errors)
    all_warnings.extend(transcript_result.warnings)

    # Validate fields
    field_errors = validate_template_fields(fields)
    for msg in field_errors:
        all_errors.append(ValidationError(
            field="fields",
            message=msg,
            error_type="invalid_config"
        ))

    # Validate PDF path
    pdf_errors = validate_pdf_path(pdf_path)
    for msg in pdf_errors:
        all_errors.append(ValidationError(
            field="pdf_path",
            message=msg,
            error_type="invalid_path"
        ))

    return ValidationResult(
        is_valid=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings
    )
