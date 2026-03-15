import json
import os
import requests
import logging
import re

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

logger = logging.getLogger(__name__)


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json=None):
        if json is None:
            json = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields  # List or dict, contains the template fields
        self._json = json.copy() if json else {}  # Create a copy to avoid shared state

    def type_check_all(self):
        if type(self._transcript_text) is not str:
            raise TypeError(
                f"ERROR in LLM() attributes ->\
                Transcript must be text. Input:\n\ttranscript_text: {self._transcript_text}"
            )
        elif type(self._target_fields) is not list:
            raise TypeError(
                f"ERROR in LLM() attributes ->\
                Target fields must be a list. Input:\n\ttarget_fields: {self._target_fields}"
            )

    def build_prompt(self, current_field):
        """
        This method is in charge of the prompt engineering. It creates a specific prompt for each target field.
        @params: current_field -> represents the current element of the json that is being prompted.
        """
        # Sanitize inputs to prevent prompt injection
        safe_field = self.sanitize_prompt_input(current_field)
        safe_text = self.sanitize_prompt_input(self._transcript_text)
        
        prompt = f""" 
            SYSTEM PROMPT:
            You are an AI assistant designed to help fillout json files with information extracted from transcribed voice recordings. 
            You will receive the transcription, and the name of the JSON field whose value you have to identify in the context. Return 
            only a single string containing the identified value for the JSON field. 
            If the field name is plural, and you identify more than one possible value in the text, return both separated by a ";".
            If you don't identify the value in the provided text, return "-1".
            ---
            DATA:
            Target JSON field to find in text: {safe_field}
            
            TEXT: {safe_text}
            """

        return prompt

    def sanitize_prompt_input(self, text):
        """
        Sanitize input to prevent prompt injection attacks
        """
        if not isinstance(text, str):
            text = str(text)
        
        # Limit length first to prevent ReDoS attacks
        if len(text) > 5000:
            text = text[:5000] + "... [TRUNCATED]"
        
        # Use pre-compiled patterns for performance
        for pattern in DANGEROUS_PROMPT_PATTERNS:
            text = pattern.sub('[FILTERED]', text)
        
        # Remove control characters
        text = CONTROL_CHARS_PATTERN.sub('', text)
        
        return text

    def main_loop(self):
        # Validate inputs before processing
        if not self._target_fields:
            raise ValueError("No target fields specified")
        
        if not self._transcript_text:
            raise ValueError("No transcript text provided")
        
        # Handle both dict and list formats for target_fields
        if isinstance(self._target_fields, list):
            # Convert list to dict for processing
            fields_dict = {field: field for field in self._target_fields}
        elif isinstance(self._target_fields, dict):
            fields_dict = self._target_fields
        else:
            raise TypeError("target_fields must be a list or dictionary")
        
        for field in fields_dict.keys():
            prompt = self.build_prompt(field)
            
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            ollama_model = os.getenv("OLLAMA_MODEL", "mistral")
            ollama_url = f"{ollama_host}/api/generate"

            payload = {
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
            }

            response = None
            try:
                response = requests.post(ollama_url, json=payload, timeout=30)
                response.raise_for_status()
                
                # Parse response
                json_data = response.json()
                
                # Validate response structure
                if "response" not in json_data:
                    logger.error(f"Invalid response format from Ollama: {json_data}")
                    parsed_response = "-1"
                else:
                    parsed_response = json_data["response"]
                
                logger.debug(f"Ollama response for field '{field}': {parsed_response}")
                self.add_response_to_json(field, parsed_response)
                
            except requests.exceptions.ConnectionError:
                logger.error(f"Could not connect to Ollama at {ollama_url}")
                raise ConnectionError(
                    f"Could not connect to Ollama at {ollama_url}. "
                    "Please ensure Ollama is running and accessible."
                )
            except requests.exceptions.HTTPError as e:
                logger.error(f"Ollama returned an error: {e}")
                raise RuntimeError(f"Ollama returned an error: {e}")
            except requests.exceptions.Timeout:
                logger.error(f"Ollama request timed out after 30 seconds")
                raise RuntimeError("Ollama request timed out")
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {e}")
                raise RuntimeError(f"Request failed: {e}")
            except (ValueError, KeyError) as e:
                logger.error(f"Error parsing Ollama response: {e}")
                # Continue with next field instead of failing completely
                self.add_response_to_json(field, "-1")
            finally:
                # Ensure response is properly closed to prevent resource leaks
                if response is not None:
                    try:
                        response.close()
                    except:
                        pass

        logger.info("LLM extraction completed")
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
        if not isinstance(value, str):
            return str(value)
        
        # Limit length first to prevent ReDoS
        if len(value) > 1000:
            logger.warning(f"Response truncated from {len(value)} to 1000 characters")
            value = value[:1000]
        
        # Use pre-compiled patterns for performance
        # Remove quotes and whitespace
        value = value.strip().replace('"', "")
        
        # Remove control characters
        value = CONTROL_CHARS_PATTERN.sub('', value)
        
        # Remove potential script tags or HTML (non-greedy pattern)
        value = HTML_TAGS_PATTERN.sub('', value)
        
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
