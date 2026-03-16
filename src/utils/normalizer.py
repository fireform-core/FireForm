import dateparser
from datetime import datetime

def normalize_date(raw_text: str, output_format: str = "%d-%m-%Y") -> str:
    # If LLM returned -1 or empty, don't try to parse
    if not raw_text or raw_text == "-1":
        return raw_text
        
    # dateparser handles "yesterday", "2 days ago", "last Friday", etc.
    parsed_date = dateparser.parse(raw_text)
    
    if parsed_date:
        return parsed_date.strftime(output_format)
    
    return raw_text # Fallback to raw text if parsing fails