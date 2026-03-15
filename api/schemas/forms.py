from pydantic import BaseModel, Field, field_validator, ConfigDict
import re
import html

# Pre-compile regex patterns for performance
DANGEROUS_CONTENT_PATTERN = re.compile(
    r'(?i)(?:'
    r'<\s*script|'
    r'javascript\s*:|'
    r'data\s*:|'
    r'vbscript\s*:|'
    r'on(?:click|error|load|mouseover|focus|blur|change|submit)\s*=|'
    r'&#\s*\d+\s*;|'
    r'&[a-z]+;.*[<>]'
    r')'
)

CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')

class FormFill(BaseModel):
    template_id: int = Field(..., gt=0, le=2147483647)
    input_text: str = Field(..., min_length=1, max_length=50000)

    @field_validator('template_id')
    @classmethod
    def validate_template_id(cls, v):
        if v is None:
            raise ValueError('Template ID cannot be null')
        if not isinstance(v, int):
            raise ValueError('Template ID must be an integer')
        return v

    @field_validator('input_text')
    @classmethod
    def validate_input_text(cls, v):
        if v is None:
            raise ValueError('Input text cannot be null')
        
        if not v.strip():
            raise ValueError('Input text cannot be empty')
        
        # Normalize and decode input
        try:
            v = html.unescape(v)
        except Exception:
            # If unescape fails, continue with original value
            pass
            
        v = v.strip()
        
        # Remove control characters
        v = CONTROL_CHARS_PATTERN.sub('', v)
        
        # Check for dangerous content
        if DANGEROUS_CONTENT_PATTERN.search(v):
            raise ValueError('Potentially dangerous content detected')
        
        # Final length check after processing
        if len(v) == 0:
            raise ValueError('Input text cannot be empty after processing')
        
        return v


class FormFillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str