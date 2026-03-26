from pydantic import BaseModel, Field, field_validator, ConfigDict
import re
import os
from pathlib import Path
import urllib.parse
import unicodedata

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
        if not v or not v.strip():
            raise ValueError('PDF path cannot be empty')
        
        # Early length check
        if len(v) > 500:
            raise ValueError('Path too long')
        
        # Unicode normalization to prevent compatibility attacks
        try:
            original_len = len(v)
            v = unicodedata.normalize('NFKC', v)
            
            # Check for suspicious expansion after normalization
            if len(v) > original_len * 1.5:
                raise ValueError('Suspicious Unicode expansion detected')
            
            # Check for dangerous Unicode categories and ranges
            for char in v:
                char_code = ord(char)
                # Fullwidth forms
                if 0xFF00 <= char_code <= 0xFF60:
                    raise ValueError('Fullwidth characters detected in path')
                # Mathematical operators that could be confused
                if 0x2200 <= char_code <= 0x22FF:
                    raise ValueError('Mathematical operator characters detected in path')
                # Various symbols that could be path separators
                if char_code in [0x2044, 0x2215, 0x29F8, 0x29F9]:  # Fraction slash, division slash, etc.
                    raise ValueError('Suspicious separator characters detected in path')
                # Zero-width and invisible characters
                if char_code in [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF]:
                    raise ValueError('Invisible characters detected in path')
                    
        except ValueError:
            # Re-raise ValueError to preserve error message
            raise
        except Exception:
            raise ValueError('Invalid Unicode characters in path')
        
        # Single round of URL decoding to prevent double-encoding attacks
        original_v = v
        try:
            v = urllib.parse.unquote(v)
            if len(v) < len(original_v) * 0.3:
                raise ValueError('Suspicious path encoding detected')
        except ValueError:
            # Re-raise ValueError to preserve original error message
            raise
        except Exception:
            raise ValueError('Invalid URL encoding in path')
        
        # Normalize path
        try:
            normalized = os.path.normpath(v)
        except Exception:
            raise ValueError('Invalid path format')
        
        # Early traversal detection on normalized path
        if ('..' in normalized or 
            normalized.startswith(('/', '\\')) or
            re.match(r'^[A-Za-z]:[\\/]', normalized, re.ASCII) or  # Windows drive letters (ASCII only)
            re.match(r'^[A-Za-z][A-Za-z0-9+.-]{0,20}://', normalized, re.ASCII)):  # URI schemes (bounded)
            raise ValueError('Path traversal detected')
        
        # Traversal pattern detection
        traversal_patterns = [
            '..', '..\\', '../', '..\\\\', '..\\/', '../\\',
            '%2e%2e', '%2e%2e%2f', '%2e%2e%5c', '%252e%252e'
        ]
        
        v_lower = v.lower()
        normalized_lower = normalized.lower()
        
        for pattern in traversal_patterns:
            if pattern in v_lower or pattern in normalized_lower:
                raise ValueError('Path traversal detected')
        
        # Check for forbidden characters
        forbidden_chars = ['~', '$', '|', '&', ';', '`', '<', '>', '"', "'", '*', '?', ':']
        forbidden_chars.extend([chr(i) for i in range(32)])  # Control characters
        forbidden_chars.append(chr(127))  # DEL character
        
        for char in forbidden_chars:
            if char in normalized:
                raise ValueError(f'Forbidden character detected: {repr(char)}')
        
        # Check if it's a PDF file
        if not normalized.lower().endswith('.pdf'):
            raise ValueError('File must be a PDF')
        
        # Check filename for Windows reserved names
        try:
            filename = Path(normalized).name
            if not filename:  # Empty filename
                raise ValueError('Empty filename detected')
            
            # Check for empty base name (e.g., ".pdf" with no actual name)
            base_name_check = filename.rsplit('.', 1)[0] if '.' in filename else filename
            if not base_name_check or base_name_check == '.' or base_name_check == '':
                raise ValueError('Invalid filename: empty base name')
            
            # Check for reserved names (case-insensitive, handle edge cases)
            filename_upper = filename.upper()
            base_name = filename_upper.split('.')[0] if '.' in filename_upper else filename_upper
            
            reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)]
            
            if base_name in reserved_names:
                raise ValueError(f'Reserved filename detected: {base_name}')
            
            # Additional checks for edge cases
            if filename.startswith('.') and len(filename) == 1:
                raise ValueError('Invalid filename: single dot')
            if filename == '..':
                raise ValueError('Invalid filename: double dot')
            if len(filename) > 255:  # Windows/Linux filename length limit
                raise ValueError('Filename too long')
                
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f'Error validating filename: {e}')
        
        # Strict prefix validation (no symlink resolution at validation time)
        allowed_prefixes = [
            'src/inputs/', 'src/templates/', 'uploads/', 'templates/',
            './src/inputs/', './src/templates/', './uploads/', './templates/',
            'src\\inputs\\', 'src\\templates\\', 'uploads\\', 'templates\\',
            '.\\src\\inputs\\', '.\\src\\templates\\', '.\\uploads\\', '.\\templates\\'
        ]
        
        normalized_forward = normalized.replace('\\', '/')
        if not any(normalized_forward.startswith(prefix.replace('\\', '/')) for prefix in allowed_prefixes):
            raise ValueError('Path must be within allowed directories (src/inputs/, src/templates/, uploads/, templates/)')
        
        # Final length check after all processing
        if len(normalized) > 400:
            raise ValueError('Path too long after processing')
        
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