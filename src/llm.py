import json
import os
import requests
import logging
import re
import html

# Compile regex patterns once for performance
CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
HTML_TAGS_PATTERN = re.compile(r'<[^>]*?>')  # Non-greedy to prevent ReDoS
DANGEROUS_PROMPT_PATTERNS = [
    re.compile(r'(?i)system\s*prompt'),
    re.compile(r'(?i)ignore\s+previous\s+instructions'),
    re.compile(r'(?i)new\s+instructions'),
    re.compile(r'(?i)assistant\s*:'),
    re.compile(r'(?i)human\s*:'),
    re.compile(r'(?i)user\s*:'),
    re.compile(r'(?i)admin\s*:'),
    re.compile(r'(?i)override'),
    re.compile(r'(?i)jailbreak'),
]

# Script patterns for response sanitization
SCRIPT_PATTERNS = [
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'data:', re.IGNORECASE),
    re.compile(r'vbscript:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),
]

# XSS patterns for input sanitization
XSS_PATTERNS = [
    re.compile(r'<\s*script\b', re.IGNORECASE),
    re.compile(r'<\s*iframe\b', re.IGNORECASE),
    re.compile(r'<\s*object\b', re.IGNORECASE),
    re.compile(r'<\s*embed\b', re.IGNORECASE),
    re.compile(r'javascript\s*:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),
]

logger = logging.getLogger(__name__)


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json=None):
        import copy
        if json is None:
            json = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields  # List or dict, contains the template fields
        self._json = copy.deepcopy(json) if json else {}  # Create a deep copy to avoid shared state

    def build_prompt(self, current_field):
        """
        This method is in charge of the prompt engineering. It creates a specific prompt for each target field.
        @params: current_field -> represents the current element of the json that is being prompted.
        """
        # Sanitize inputs to prevent prompt injection
        sanitized_field = self.sanitize_prompt_input(current_field)
        sanitized_text = self.sanitize_prompt_input(self._transcript_text)
        
        prompt = f""" 
            SYSTEM PROMPT:
            You are an AI assistant designed to help fillout json files with information extracted from transcribed voice recordings. 
            You will receive the transcription, and the name of the JSON field whose value you have to identify in the context. Return 
            only a single string containing the identified value for the JSON field. 
            If the field name is plural, and you identify more than one possible value in the text, return both separated by a ";".
            If you don't identify the value in the provided text, return "-1".
            ---
            DATA:
            Target JSON field to find in text: {sanitized_field}
            
            TEXT: {sanitized_text}
            """

        return prompt

    def sanitize_prompt_input(self, text):
        """
        Sanitize input to prevent prompt injection attacks
        """
        if not isinstance(text, str):
            text = str(text)
        
        # Early length check
        if len(text) > 10000:
            logger.warning("Input text too long, truncating")
            text = text[:10000] + "... [TRUNCATED]"
        
        # Store original for comparison
        original_text = text
        
        # Normalization and decoding with limits
        timer = None
        timeout_occurred = [False]  # Use list for mutable reference
        
        try:
            import unicodedata
            import urllib.parse
            import threading
            import time
            
            def timeout_handler():
                timeout_occurred[0] = True
            
            # Set timeout for processing using threading.Timer
            timer = threading.Timer(2.0, timeout_handler)
            timer.start()
            start_time = time.time()
            
            try:
                # Normalize using NFC to prevent compatibility attacks
                text = unicodedata.normalize('NFC', text)
                
                # Check timeout periodically to avoid race conditions
                if time.time() - start_time > 1.8 or timeout_occurred[0]:
                    logger.warning("Processing timeout during normalization")
                    return "User input has been sanitized for security reasons."
                
                # Check for suspicious expansion
                if len(text) > len(original_text) * 2:
                    logger.warning("Suspicious Unicode expansion detected")
                    return "User input has been sanitized for security reasons."
                
                # Single URL decode only
                decoded = urllib.parse.unquote(text)
                if len(decoded) < len(text) * 0.5:
                    logger.warning("Suspicious URL encoding detected")
                    return "User input has been sanitized for security reasons."
                text = decoded
                
                # Check timeout again
                if time.time() - start_time > 1.8 or timeout_occurred[0]:
                    logger.warning("Processing timeout during URL decoding")
                    return "User input has been sanitized for security reasons."
                
                # HTML unescape with caution
                unescaped = html.unescape(text)
                if len(unescaped) > len(text) * 3:
                    logger.warning("Suspicious HTML entity expansion detected")
                    return "User input has been sanitized for security reasons."
                text = unescaped
                
                # Final timeout check
                if time.time() - start_time > 1.8 or timeout_occurred[0]:
                    logger.warning("Processing timeout during HTML unescaping")
                    return "User input has been sanitized for security reasons."
                    
            except (ValueError, TypeError, AttributeError) as e:
                if time.time() - start_time > 1.8 or timeout_occurred[0]:
                    logger.warning("Processing timeout during exception handling")
                    return "User input has been sanitized for security reasons."
                logger.warning(f"Input processing error: {e}", exc_info=True)
                raise ValueError("Input processing failed") from e
            except Exception as e:
                if time.time() - start_time > 1.8 or timeout_occurred[0]:
                    logger.warning("Processing timeout during exception handling")
                    return "User input has been sanitized for security reasons."
                logger.error(f"Unexpected error during input processing: {e}", exc_info=True)
                raise RuntimeError("Input processing failed") from e
                
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Input normalization failed: {e}", exc_info=True)
            # Continue with original text
            text = original_text
        except Exception as e:
            logger.error(f"Unexpected error in input normalization: {e}", exc_info=True)
            # Continue with original text
            text = original_text
        finally:
            # Cancel timer to prevent resource leaks
            if timer is not None:
                try:
                    timer.cancel()
                except Exception as e:
                    logger.debug(f"Failed to cancel timer: {e}")
                    # Don't raise - cleanup should be best effort
        
        # Check for suspicious patterns
        suspicious_found = False
        
        # Check for XSS patterns first
        for pattern in XSS_PATTERNS:
            if pattern.search(original_text) or pattern.search(text):
                suspicious_found = True
                logger.warning("XSS pattern detected in input")
                break
        
        # Check original text for prompt injection
        if not suspicious_found:
            for pattern in DANGEROUS_PROMPT_PATTERNS:
                if pattern.search(original_text):
                    suspicious_found = True
                    logger.warning("Suspicious pattern detected in input")
                    break
        
        # Check processed text for prompt injection
        if not suspicious_found:
            for pattern in DANGEROUS_PROMPT_PATTERNS:
                if pattern.search(text):
                    suspicious_found = True
                    logger.warning("Suspicious pattern detected in processed input")
                    break
        
        # Token/sequencing checks for instruction-like content
        if not suspicious_found:
            instruction_tokens = [
                'ignore', 'forget', 'disregard', 'override', 'system:', 'assistant:', 
                'user:', 'human:', 'new instructions', 'act as', 'pretend to be'
            ]
            
            text_lower = text.lower()
            for token in instruction_tokens:
                if token in text_lower:
                    suspicious_found = True
                    logger.warning("Instruction-like content detected")
                    break
        
        # Process suspicious content
        if suspicious_found:
            # Log the attempt for monitoring (without revealing content)
            logger.warning("Potential prompt injection attempt blocked")
            
            # Return fallback for suspicious content
            return "User input has been sanitized for security reasons."
        
        # Clean control characters
        text = CONTROL_CHARS_PATTERN.sub('', text)
        
        # Final length check
        if len(text) > 5000:
            text = text[:5000] + "... [TRUNCATED]"
        
        return text.strip()

    def main_loop(self):
        # Input validation
        if not self._target_fields:
            raise ValueError("No target fields specified")
        
        if not self._transcript_text:
            raise ValueError("No transcript text provided")
        
        # Support both dict and list formats for target_fields
        if isinstance(self._target_fields, list):
            # Convert list to dict for processing
            fields_dict = {field: field for field in self._target_fields}
        elif isinstance(self._target_fields, dict):
            fields_dict = self._target_fields
        else:
            raise TypeError("target_fields must be a list or dictionary")
        
        # Limit number of fields to prevent resource exhaustion
        if len(fields_dict) > 20:
            logger.warning(f"Too many fields ({len(fields_dict)}), limiting to 20")
            fields_dict = dict(list(fields_dict.items())[:20])
        
        # Use session for connection reuse and proper resource management
        session = requests.Session()
        
        # Configure session with proper limits
        session.headers.update({
            'User-Agent': 'FireForm/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        # Set connection pool limits to prevent resource exhaustion
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=0
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        processed_fields = 0
        max_fields_per_session = 10
        
        try:
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            ollama_model = os.getenv("OLLAMA_MODEL", "mistral")
            ollama_url = f"{ollama_host}/api/generate"
            
            # Check Ollama URL format
            if not ollama_url.startswith(('http://', 'https://')):
                raise ValueError("Invalid Ollama URL format")

            for field in fields_dict.keys():
                if processed_fields >= max_fields_per_session:
                    logger.warning(f"Reached maximum fields per session: {max_fields_per_session}")
                    break
                
                prompt = self.build_prompt(field)
                
                # Check prompt length
                if len(prompt) > 50000:  # 50KB limit
                    logger.error(f"Prompt too long for field '{field}', skipping")
                    self.add_response_to_json(field, "-1")
                    continue
                
                payload = {
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                }

                response = None
                try:
                    # Add request timeout and size limits
                    response = session.post(
                        ollama_url, 
                        json=payload, 
                        timeout=30,
                        stream=False
                    )
                    response.raise_for_status()
                    
                    content_length = response.headers.get('content-length')
                    if content_length:
                        try:
                            content_length = int(content_length)
                            if content_length > 1024 * 1024:  # 1MB limit
                                logger.error(f"Response too large ({content_length} bytes) for field '{field}', skipping")
                                self.add_response_to_json(field, "-1")
                                continue
                        except (ValueError, TypeError):
                            logger.warning("Invalid content-length header")
                    
                    # Read response with size limit to prevent memory exhaustion
                    try:
                        response_text = response.text
                        if len(response_text) > 1024 * 1024:  # 1MB limit on actual content
                            logger.error(f"Response content too large ({len(response_text)} bytes) for field '{field}', skipping")
                            self.add_response_to_json(field, "-1")
                            continue
                        
                        if not response_text.strip():
                            logger.warning(f"Empty response for field '{field}'")
                            self.add_response_to_json(field, "-1")
                            continue
                        
                        json_data = response.json()
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to parse JSON response for field '{field}': {e}")
                        self.add_response_to_json(field, "-1")
                        continue
                    except Exception as e:
                        logger.error(f"Unexpected error parsing response for field '{field}': {e}", exc_info=True)
                        self.add_response_to_json(field, "-1")
                        continue
                    
                    # Check response structure with error handling
                    try:
                        if not isinstance(json_data, dict):
                            logger.error(f"Response is not a JSON object for field '{field}'")
                            parsed_response = "-1"
                        elif "response" not in json_data:
                            logger.error(f"Invalid response format from Ollama - missing 'response' field for field '{field}'")
                            parsed_response = "-1"
                        else:
                            parsed_response = json_data["response"]
                            # Convert response to string for processing
                            if parsed_response is None:
                                parsed_response = ""
                            elif not isinstance(parsed_response, (str, int, float, bool)):
                                # Convert complex objects to string
                                try:
                                    parsed_response = str(parsed_response)
                                except (ValueError, TypeError, AttributeError) as e:
                                    logger.warning(f"Failed to convert response to string for field '{field}': {e}", exc_info=True)
                                    parsed_response = "-1"
                                except Exception as e:
                                    logger.error(f"Unexpected error converting response to string for field '{field}': {e}", exc_info=True)
                                    parsed_response = "-1"
                            else:
                                parsed_response = str(parsed_response)
                            
                            # Limit response size with proper bounds checking
                            if len(parsed_response) > 10000:
                                logger.warning(f"Response too long ({len(parsed_response)} chars) for field '{field}', truncating to 10000")
                                parsed_response = parsed_response[:9997] + "..."  # Exactly 10000 chars
                    
                    except (ValueError, TypeError, AttributeError, KeyError) as e:
                        logger.error(f"Error processing response structure for field '{field}': {e}", exc_info=True)
                        parsed_response = "-1"
                    except Exception as e:
                        logger.error(f"Unexpected error processing response structure for field '{field}': {e}", exc_info=True)
                        parsed_response = "-1"
                    
                    logger.debug(f"Ollama response for field '{field}': {parsed_response[:100]}...")
                    self.add_response_to_json(field, parsed_response)
                    processed_fields += 1
                    
                except requests.exceptions.ConnectionError as e:
                    logger.error(f"Could not connect to Ollama at {ollama_url}: {e}")
                    raise ConnectionError(
                        f"Could not connect to Ollama at {ollama_url}. "
                        "Please ensure Ollama is running and accessible."
                    )
                except requests.exceptions.HTTPError as e:
                    logger.error(f"Ollama returned an error for field '{field}': {e}")
                    # Continue with next field instead of failing completely
                    self.add_response_to_json(field, "-1")
                    continue
                except requests.exceptions.Timeout as e:
                    logger.error(f"Ollama request timed out after 30 seconds for field '{field}': {e}")
                    # Continue with next field instead of failing completely
                    self.add_response_to_json(field, "-1")
                    continue
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request error for field '{field}': {e}")
                    # Continue with next field instead of failing completely
                    self.add_response_to_json(field, "-1")
                    continue
                except (ValueError, KeyError) as e:
                    logger.error(f"Error parsing Ollama response for field '{field}': {e}")
                    # Continue with next field instead of failing completely
                    self.add_response_to_json(field, "-1")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error processing field '{field}': {e}", exc_info=True)
                    # Continue with next field instead of failing completely
                    self.add_response_to_json(field, "-1")
                    continue
                finally:
                    # Close response to prevent resource leaks
                    if response is not None:
                        try:
                            response.close()
                        except Exception:
                            pass  # Ignore cleanup errors
        
        except Exception as e:
            logger.error(f"Critical error in main_loop: {e}", exc_info=True)
            raise RuntimeError("LLM processing failed") from e
        finally:
            # Close session to prevent connection leaks
            try:
                session.close()
            except Exception:
                pass  # Ignore cleanup errors

        logger.info(f"LLM extraction completed - processed {processed_fields} fields")
        logger.debug(f"Extracted data: {json.dumps(self._json, indent=2)}")

        return self

    def add_response_to_json(self, field, value):
        """
        this method adds the following value under the specified field,
        or under a new field if the field doesn't exist, to the json dict
        """
        # Sanitize and validate the response
        value = self.sanitize_response(value)
        
        # Initialize parsed_value to the original value
        parsed_value = value
        
        # Only handle plural values if not "-1" and contains semicolon
        if ";" in value and value != "-1":
            parsed_value = self.handle_plural_values(value)

        # Consistent field handling - always use lists for multiple values
        if field in self._json:
            # Field already exists
            existing_value = self._json[field]
            
            if isinstance(existing_value, list):
                # Already a list, append to it
                if isinstance(parsed_value, list):
                    existing_value.extend(parsed_value)
                else:
                    existing_value.append(parsed_value)
            else:
                # Convert to list and add new value
                if isinstance(parsed_value, list):
                    self._json[field] = [existing_value] + parsed_value
                else:
                    self._json[field] = [existing_value, parsed_value]
        else:
            # New field
            if isinstance(parsed_value, list):
                self._json[field] = parsed_value
            else:
                # Store as single value, not list, for simplicity
                self._json[field] = parsed_value

        return

    def sanitize_response(self, value):
        """
        Sanitize AI response to prevent injection and ensure data quality
        """
        if value is None:
            return "-1"
        
        if not isinstance(value, str):
            value = str(value)
        
        # Limit length first to prevent ReDoS and memory issues
        if len(value) > 1000:
            logger.warning(f"Response truncated from {len(value)} to 1000 characters")
            value = value[:997] + "..."  # Exactly 1000 chars
        
        # Unicode normalization to prevent normalization attacks
        try:
            import unicodedata
            value = unicodedata.normalize('NFKC', value)
        except Exception:
            logger.warning("Unicode normalization failed, using original value")
        
        # Remove quotes and excessive whitespace
        value = value.strip().replace('"', "").replace("'", "")
        
        # Remove control characters (including Unicode control chars)
        value = CONTROL_CHARS_PATTERN.sub('', value)
        
        # Remove potential HTML tags (non-greedy pattern)
        value = HTML_TAGS_PATTERN.sub('', value)
        
        # Check for prompt injection patterns
        for pattern in DANGEROUS_PROMPT_PATTERNS:
            if pattern.search(value):
                logger.warning(f"Potential prompt injection detected in response: {value[:50]}...")
                return "-1"
        
        # Remove potential script content
        for pattern in SCRIPT_PATTERNS:
            value = pattern.sub('', value)
        
        # Final cleanup
        value = value.strip()
        
        # Return default if empty after sanitization
        if not value:
            return "-1"
        
        return value

    def handle_plural_values(self, plural_value):
        """
        This method handles plural values.
        Takes in strings of the form 'value1; value2; value3; ...; valueN'
        returns a list with the respective values -> [value1, value2, value3, ..., valueN]
        """
        if ";" not in plural_value:
            raise ValueError(
                f"Value is not plural, doesn't have ; separator, Value: {plural_value}"
            )

        logger.debug(f"Formatting plural values for JSON: {plural_value}")
        values = plural_value.split(";")

        # Clean all values properly (fix off-by-one error)
        cleaned_values = []
        for value in values:
            cleaned_value = value.strip()
            if cleaned_value:  # Only add non-empty values
                cleaned_values.append(cleaned_value)

        logger.debug(f"Resulting formatted list of values: {cleaned_values}")

        # Return empty list if no valid values found
        return cleaned_values if cleaned_values else ["-1"]

    def get_data(self):
        return self._json

    def extract_structured(self):
        """
        Attempt structured JSON extraction in a single LLM call.
        This is the new schema-driven approach that extracts all fields at once.
        """
        if not self._target_fields:
            raise ValueError("No target fields specified")
        
        if not self._transcript_text:
            raise ValueError("No transcript text provided")
        
        # Support both dict and list formats
        if isinstance(self._target_fields, list):
            schema_fields = self._target_fields
        elif isinstance(self._target_fields, dict):
            schema_fields = list(self._target_fields.keys())
        else:
            raise TypeError("target_fields must be a list or dictionary")
        
        # Limit number of fields
        if len(schema_fields) > 20:
            logger.warning(f"Too many fields ({len(schema_fields)}), limiting to 20")
            schema_fields = schema_fields[:20]
        
        # Sanitize transcript
        sanitized_text = self.sanitize_prompt_input(self._transcript_text)
        
        # Build structured extraction prompt
        prompt = f"""Extract structured JSON for these fields: {schema_fields}

Text: {sanitized_text}

Return ONLY valid JSON with the exact field names provided. If a field value is not found, use "-1".
Example format: {{"field1": "value1", "field2": "value2"}}

JSON:"""
        
        # Check prompt length
        if len(prompt) > 50000:
            raise ValueError("Prompt too long for structured extraction")
        
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_model = os.getenv("OLLAMA_MODEL", "mistral")
        ollama_url = f"{ollama_host}/api/generate"
        
        # Check URL format
        if not ollama_url.startswith(('http://', 'https://')):
            raise ValueError("Invalid Ollama URL format")
        
        payload = {
            "model": ollama_model,
            "prompt": prompt,
            "stream": False,
        }
        
        response = None
        session = None
        try:
            # Use session for proper resource management
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'FireForm/1.0',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            })
            
            response = session.post(ollama_url, json=payload, timeout=30)
            response.raise_for_status()
            
            # Check response size
            content_length = response.headers.get('content-length')
            if content_length:
                try:
                    content_length = int(content_length)
                    if content_length > 1024 * 1024:  # 1MB limit
                        raise ValueError(f"Response too large: {content_length} bytes")
                except (ValueError, TypeError) as e:
                    if "Response too large" in str(e):
                        raise
                    logger.warning("Invalid content-length header")
            
            # Read response with size limit
            response_text = response.text
            if len(response_text) > 1024 * 1024:  # 1MB limit
                raise ValueError(f"Response content too large: {len(response_text)} bytes")
            
            if not response_text.strip():
                raise ValueError("Empty response from Ollama")
            
            json_data = response.json()
            
            if not isinstance(json_data, dict):
                raise ValueError("Response is not a JSON object")
            
            if "response" not in json_data:
                raise ValueError("Invalid response format - missing 'response' field")
            
            return json_data["response"]
                    
        except requests.exceptions.Timeout:
            logger.error("Structured extraction timed out")
            raise TimeoutError("Structured extraction timed out")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Ollama: {e}")
            raise ConnectionError(f"Could not connect to Ollama at {ollama_url}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"Ollama returned an error: {e}")
            raise RuntimeError(f"Ollama error: {e}")
        except (ValueError, TypeError) as e:
            logger.error(f"Validation error in structured extraction: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in structured extraction: {e}", exc_info=True)
            raise RuntimeError(f"Structured extraction failed: {e}")
        finally:
            # Ensure resources are always cleaned up
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    def extract_structured_safe(self):
        """
        Safe wrapper for structured extraction with fallback to old method.
        Returns True if structured extraction succeeded, False if fallback needed.
        """
        try:
            logger.info("Attempting structured extraction...")
            raw_response = self.extract_structured()
            
            # Validate response is not empty
            if not raw_response or not raw_response.strip():
                logger.warning("Empty response from structured extraction")
                return False
            
            # Try to parse JSON response with multiple strategies
            cleaned_response = raw_response.strip()
            
            # Strategy 1: Remove markdown code blocks
            if "```json" in cleaned_response:
                # Extract content between ```json and ```
                start = cleaned_response.find("```json") + 7
                end = cleaned_response.find("```", start)
                if end > start:
                    cleaned_response = cleaned_response[start:end].strip()
            elif cleaned_response.startswith("```"):
                # Remove generic code blocks
                cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()
            
            # Strategy 2: Extract JSON object if embedded in text
            if not cleaned_response.startswith("{"):
                # Try to find JSON object in response
                start_idx = cleaned_response.find("{")
                end_idx = cleaned_response.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    cleaned_response = cleaned_response[start_idx:end_idx+1]
                else:
                    logger.warning("No JSON object found in response")
                    return False
            
            # Limit size before parsing
            if len(cleaned_response) > 100000:  # 100KB limit
                logger.warning(f"Cleaned response too large: {len(cleaned_response)} bytes")
                return False
            
            # Parse JSON
            try:
                parsed_data = json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON: {e}")
                logger.debug(f"Attempted to parse: {cleaned_response[:200]}...")
                return False
            
            # Validate it's a dict
            if not isinstance(parsed_data, dict):
                logger.warning(f"Structured extraction returned {type(parsed_data)}, expected dict")
                return False
            
            # Validate all required fields are present
            if isinstance(self._target_fields, list):
                required_fields = set(self._target_fields)
            elif isinstance(self._target_fields, dict):
                required_fields = set(self._target_fields.keys())
            else:
                required_fields = set()
            
            extracted_fields = set(parsed_data.keys())
            missing_fields = required_fields - extracted_fields
            
            if missing_fields:
                logger.warning(f"Missing fields in structured extraction: {missing_fields}")
                # Add missing fields with default value
                for field in missing_fields:
                    parsed_data[field] = "-1"
            
            # Sanitize all values
            sanitized_data = {}
            for key, value in parsed_data.items():
                # Only process fields we requested
                if key in required_fields:
                    if isinstance(value, str):
                        sanitized_data[key] = self.sanitize_response(value)
                    elif value is None:
                        sanitized_data[key] = "-1"
                    elif isinstance(value, (int, float, bool)):
                        sanitized_data[key] = self.sanitize_response(str(value))
                    elif isinstance(value, list):
                        # Limit list size to prevent memory exhaustion
                        if len(value) > 100:
                            logger.warning(f"List too large for field '{key}': {len(value)} items, limiting to 100")
                            value = value[:100]
                        
                        # Handle list values
                        sanitized_list = []
                        for item in value:
                            if isinstance(item, str):
                                sanitized_list.append(self.sanitize_response(item))
                            else:
                                sanitized_list.append(self.sanitize_response(str(item)))
                        sanitized_data[key] = sanitized_list if sanitized_list else ["-1"]
                    else:
                        # Convert complex objects to string
                        sanitized_data[key] = self.sanitize_response(str(value))
            
            # Verify all required fields are present
            missing_required = required_fields - set(sanitized_data.keys())
            if missing_required:
                logger.warning(f"Missing required fields after sanitization: {missing_required}")
                return False
            
            self._json = sanitized_data
            logger.info(f"Structured extraction succeeded - extracted {len(sanitized_data)} fields")
            return True
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse structured JSON: {e}")
            return False
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Validation error in structured extraction: {e}")
            return False
        except Exception as e:
            logger.warning(f"Structured extraction failed: {e}", exc_info=True)
            return False
