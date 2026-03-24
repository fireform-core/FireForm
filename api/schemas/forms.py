from pydantic import BaseModel, Field, field_validator, ConfigDict
import re
import html
import logging
import unicodedata
import urllib.parse

# Get logger for this module
logger = logging.getLogger(__name__)

# Optional bleach import for HTML sanitization
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False

# Pre-compile regex patterns for performance
DANGEROUS_CONTENT_PATTERN = re.compile(
    r'(?i)(?:'
    r'<\s*(?:script|iframe|object|embed|form|input|meta|link|style|base|applet|body|html|head|title|svg|math|xml)\b|'
    r'javascript\s*:|'
    r'data\s*:|'
    r'vbscript\s*:|'
    r'file\s*:|'
    r'ftp\s*:|'
    r'on(?:click|error|load|mouseover|focus|blur|change|submit|keydown|keyup|keypress|resize|scroll|unload|beforeunload|hashchange|popstate|storage|message|offline|online|pagehide|pageshow|beforeprint|afterprint|dragstart|drag|dragenter|dragover|dragleave|drop|dragend|copy|cut|paste|selectstart|select|input|invalid|reset|search|abort|canplay|canplaythrough|durationchange|emptied|ended|loadeddata|loadedmetadata|loadstart|pause|play|playing|progress|ratechange|seeked|seeking|stalled|suspend|timeupdate|volumechange|waiting|animationstart|animationend|animationiteration|transitionend|wheel|contextmenu|show|toggle)\s*=|'
    r'&#\s*(?:\d{1,7}|x[0-9a-f]{1,6})\s*;|'
    r'expression\s*\(|'
    r'url\s*\(|'
    r'import\s*\(|'
    r'@import\b|'
    r'binding\s*:|'
    r'behavior\s*:|'
    r'mocha\s*:|'
    r'livescript\s*:|'
    r'eval\s*\(|'
    r'setTimeout\s*\(|'
    r'setInterval\s*\(|'
    r'Function\s*\(|'
    r'constructor\s*\(|'
    r'alert\s*\(|'
    r'confirm\s*\(|'
    r'prompt\s*\(|'
    r'document\.\w+\s*[\(\[=]|'
    r'window\.\w+\s*[\(\[=]|'
    r'location\.|'
    r'navigator\.|'
    r'history\.|'
    r'localStorage\.|'
    r'sessionStorage\.|'
    r'XMLHttpRequest\b|'
    r'fetch\s*\(|'
    r'WebSocket\b|'
    r'EventSource\b|'
    r'SharedWorker\b|'
    r'\bWorker\b|'
    r'\bServiceWorker\b|'
    r'postMessage\b|'
    r'innerHTML\b|'
    r'outerHTML\b|'
    r'insertAdjacentHTML\b|'
    r'document\.write\b|'
    r'document\.writeln\b|'
    r'createContextualFragment\b|'
    r'DOMParser\b|'
    r'Range\.createContextualFragment\b|'
    r'<\s*!\s*\[CDATA\[|'
    r'<\s*!\s*--.*?--|'
    r'<\s*\?.*?\?>'
    r')', re.DOTALL
)

# Control character pattern including Unicode control chars
CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F\u2000-\u200F\u2028-\u202F\u205F-\u206F\uFEFF]')

# Path traversal pattern (compiled for performance)
PATH_TRAVERSAL_PATTERN = re.compile(r'(?i)(?:\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c|\.\.%2f|\.\.%5c)')

# Pattern for detecting potential prompt injection
PROMPT_INJECTION_PATTERN = re.compile(
    r'(?i)(?:'
    r'(?:please\s+)?ignore\s+(?:all\s+)?(?:previous|above|all|the|your|system|earlier|prior)\s+(?:instructions?|prompts?|commands?|rules?|directions?)|'
    r'(?:please\s+)?forget\s+(?:all\s+)?(?:previous|above|all|the|your|system|earlier|prior)\s+(?:instructions?|prompts?|commands?|rules?|directions?)|'
    r'(?:please\s+)?disregard\s+(?:all\s+)?(?:previous|above|all|the|your|system|earlier|prior|everything)\s*(?:instructions?|prompts?|commands?|rules?|directions?|and)?|'
    r'(?:please\s+)?override\s+(?:all\s+)?(?:previous|above|all|the|your|system|earlier|prior)\s+(?:instructions?|prompts?|commands?|rules?|directions?)|'
    r'new\s+(?:instructions?|prompts?|commands?|rules?|directions?)|'
    r'(?:^|\s|["\'\[\(])(?:system|assistant|user|human|ai|bot)\s*:\s*|'
    r'(?:^|\s)(?:now\s+)?(?:you\s+(?:are|will|must|should)|act\s+as|pretend\s+to\s+be|roleplay\s+as)|'
    r'(?:^|\s)(?:from\s+now\s+on|instead\s+of|rather\s+than)(?:\s|$)|'
    r'actually\s+you\s+(?:are|will|must|should)|'
    r'in\s+reality\s+you\s+(?:are|will|must|should)|'
    r'the\s+truth\s+is|'
    r'actually\s+ignore|'
    r'but\s+ignore|'
    r'however\s+ignore|'
    r'nevertheless\s+ignore|'
    r'nonetheless\s+ignore|'
    r'still\s+ignore|'
    r'yet\s+ignore|'
    r'although\s+ignore|'
    r'though\s+ignore|'
    r'despite\s+ignore|'
    r'in\s+spite\s+of\s+ignore|'
    r'regardless\s+ignore|'
    r'irrespective\s+ignore|'
    r'notwithstanding\s+ignore|'
    r'(?:can\s+you|i\s+need\s+you\s+to)\s+(?:ignore|forget|disregard)'
    r')'
)

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
        
        # Early length check to prevent processing attacks
        if len(v) > 50000:
            raise ValueError('Input text too long')
        
        # Check for dangerous content before normalization
        if DANGEROUS_CONTENT_PATTERN.search(v):
            raise ValueError('Potentially dangerous content detected')
        
        # Check for zero-width and invisible characters
        invisible_chars = ['\u200B', '\u200C', '\u200D', '\u2060', '\uFEFF', '\u202E']
        if any(char in v for char in invisible_chars):
            raise ValueError('Invisible or zero-width characters detected')
        
        # Check for homograph attacks (optimized)
        suspicious_chars = {'і', 'ο', 'О', 'а', 'е', 'р', 'с', 'х'}  # Use set for O(1) lookup
        
        # Single pass check for mixed scripts
        has_latin = False
        has_suspicious = False
        for char in v:
            if char in suspicious_chars:
                has_suspicious = True
                if has_latin:  # Early exit if both found
                    raise ValueError('Potential homograph attack detected')
            elif char.isascii() and char.isalpha():
                has_latin = True
                if has_suspicious:  # Early exit if both found
                    raise ValueError('Potential homograph attack detected')
        
        # Check for path traversal patterns (optimized)
        if PATH_TRAVERSAL_PATTERN.search(v):
            raise ValueError('Path traversal pattern detected')
        
        # Check for control characters and null bytes
        if any(ord(c) < 32 and c not in '\t\n\r' for c in v):
            raise ValueError('Control characters or null bytes detected')
        
        # Unicode normalization with strict expansion protection
        try:
            # Use NFC instead of NFKC to prevent compatibility attacks
            normalized = unicodedata.normalize('NFC', v)
            
            # Check for suspicious Unicode patterns before normalization
            # Detect combining character attacks (many combining chars per base char)
            combining_chars = sum(1 for c in v if unicodedata.combining(c))
            base_chars = len(v) - combining_chars
            if base_chars > 0 and combining_chars / base_chars > 0.5:  # More than 0.5 combining per base
                raise ValueError('Suspicious Unicode combining character pattern detected')
            
            # Check for Unicode expansion attacks
            if len(normalized) > len(v) * 1.5:
                raise ValueError('Suspicious Unicode normalization expansion detected')
            
            # Also check for excessive compression (potential DoS)
            if len(normalized) < len(v) * 0.3 and len(v) > 1000:
                raise ValueError('Suspicious Unicode normalization compression detected')
            
            # Apply normalized result
            v = normalized
            
            # URL decode to catch encoded injection attempts
            decoded = urllib.parse.unquote(v)
            
            # Check for URL decoding expansion
            if len(decoded) > len(v) * 2:
                raise ValueError('Suspicious URL decoding expansion detected')
            
            # Check decoded content for dangerous patterns
            if DANGEROUS_CONTENT_PATTERN.search(decoded):
                raise ValueError('Potentially dangerous content detected after URL decoding')
                
            # Length check after all processing
            if len(v) > 45000:  # Reduced from original to account for processing
                raise ValueError('Input text too long after normalization')
                
        except ValueError:
            # Re-raise ValueError to preserve security error messages
            raise
        except Exception:
            raise ValueError('Invalid Unicode characters detected')
        
        # Simplified HTML entity decoding
        try:
            v = html.unescape(v)
        except Exception:
            raise ValueError('HTML entity decoding failed')
            
        v = v.strip()
        
        # Remove control characters
        v = CONTROL_CHARS_PATTERN.sub('', v)
        
        # Use bleach if available
        if BLEACH_AVAILABLE:
            try:
                v = bleach.clean(v, tags=[], attributes={}, strip=True)
            except Exception as e:
                logger.error(f"bleach.clean failed: {str(e)}", exc_info=True)
                pass
        
        # Final dangerous content check after processing
        if DANGEROUS_CONTENT_PATTERN.search(v):
            raise ValueError('Potentially dangerous content detected after processing')
        
        # Check for prompt injection attempts
        if PROMPT_INJECTION_PATTERN.search(v):
            raise ValueError('Potential prompt injection detected')
        
        # Final validation
        if len(v) == 0:
            raise ValueError('Input text cannot be empty after processing')
        
        # Additional length check for processed content
        if len(v) > 45000:  # Leave buffer for processing
            raise ValueError('Input text too long after processing')
        
        return v


class FormFillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    template_id: int
    input_text: str
    output_pdf_path: str