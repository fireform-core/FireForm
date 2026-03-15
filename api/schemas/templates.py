from pydantic import BaseModel, Field, field_validator, ConfigDict
import re

class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    pdf_path: str = Field(..., min_length=1, max_length=500)
    fields: dict = Field(...)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not re.match(r'^[a-zA-Z0-9\s_-]+$', v):
            raise ValueError('Name can only contain letters, numbers, spaces, underscores, and hyphens')
        return v

    @field_validator('pdf_path')
    @classmethod
    def validate_pdf_path(cls, v):
        import os
        from pathlib import Path
        import urllib.parse
        
        # Decode any URL encoding
        v = urllib.parse.unquote(v)
        
        # Normalize path to handle various traversal attempts
        normalized = os.path.normpath(v)
        
        # Convert to Path object for safer handling and use resolved path
        try:
            resolved_path = Path(normalized).resolve()
        except (OSError, ValueError):
            raise ValueError('Invalid file path format')
        
        # Check for traversal attempts (more comprehensive)
        if '..' in normalized or normalized.startswith('/') or normalized.startswith('\\'):
            raise ValueError('Path traversal detected')
        
        # Check for absolute paths on Windows
        if os.path.isabs(normalized):
            raise ValueError('Absolute paths not allowed')
        
        # Ensure it's a PDF file
        if not normalized.lower().endswith('.pdf'):
            raise ValueError('File must be a PDF')
        
        # Additional security checks
        forbidden_patterns = ['..', '~', '$', '|', '&', ';', '`', '(', ')', '{', '}', '[', ']']
        for pattern in forbidden_patterns:
            if pattern in normalized:
                raise ValueError(f'Forbidden character or pattern detected: {pattern}')
        
        # Ensure path is within allowed directory structure
        allowed_prefixes = ['src/', 'uploads/', 'templates/', './src/', './uploads/', './templates/', 'src\\', '.\\src\\']
        if not any(normalized.replace('\\', '/').startswith(prefix.replace('\\', '/')) for prefix in allowed_prefixes):
            raise ValueError('Path must be within allowed directories')
        
        return normalized

    @field_validator('fields')
    @classmethod
    def validate_fields(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Fields must be a dictionary')
        
        if len(v) > 50:
            raise ValueError('Too many fields: maximum 50 allowed')
            
        for key, value in v.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError('Field keys and values must be strings')
            if len(key) > 100 or len(value) > 500:
                raise ValueError('Field names or values too long')
        return v

class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    pdf_path: str
    fields: dict