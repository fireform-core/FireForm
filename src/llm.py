import json
import os
import requests


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json=None, use_batch_processing=True):
        if json is None:
            json = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields  # List or Dict, contains the template fields
        self._json = json  # dictionary
        self._use_batch_processing = use_batch_processing  # bool, whether to use O(1) batch processing

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

    def build_batch_prompt(self, fields_list):
        """
        Build a single prompt that requests all fields at once for O(1) batch processing.
        This dramatically reduces processing time by eliminating N sequential API calls.
        
        @params: fields_list -> list of all field names to extract
        @returns: prompt string for batch extraction
        """
        fields_formatted = "\n".join([f"  - {field}" for field in fields_list])
        
        prompt = f"""
SYSTEM PROMPT:
You are an AI assistant designed to extract structured information from transcribed voice recordings.
You will receive a transcript and a list of JSON fields to extract. Return ONLY a valid JSON object with the extracted values.

INSTRUCTIONS:
- Return a valid JSON object with field names as keys and extracted values as strings
- If a field name is plural and you identify multiple values, separate them with ";"
- If you cannot find information for a field, use "-1" as the value
- Be precise and extract only relevant information for each field
- Do not include explanations, markdown formatting, or additional text
- The response must be valid JSON that can be parsed directly

FIELDS TO EXTRACT:
{fields_formatted}

TEXT:
{self._transcript_text}

Return only the JSON object:
"""
        
        return prompt

    def build_prompt(self, current_field):
        """
        This method is in charge of the prompt engineering. It creates a specific prompt for each target field.
        @params: current_field -> represents the current element of the json that is being prompted.
        """
        prompt = f""" 
            SYSTEM PROMPT:
            You are an AI assistant designed to help fillout json files with information extracted from transcribed voice recordings. 
            You will receive the transcription, and the name of the JSON field whose value you have to identify in the context. Return 
            only a single string containing the identified value for the JSON field. 
            If the field name is plural, and you identify more than one possible value in the text, return both separated by a ";".
            If you don't identify the value in the provided text, return "-1".
            ---
            DATA:
            Target JSON field to find in text: {current_field}
            
            TEXT: {self._transcript_text}
            """

        return prompt

    def main_loop(self):
        """
        Main extraction loop. Uses batch processing (O(1)) by default for better performance,
        or falls back to sequential processing (O(N)) if batch mode is disabled.
        """
        # Handle both dict and list formats for target_fields
        if isinstance(self._target_fields, dict):
            fields_to_process = list(self._target_fields.keys())
        else:
            fields_to_process = list(self._target_fields)
        
        if self._use_batch_processing:
            print(f"[LOG] Using batch processing for {len(fields_to_process)} fields (O(1) optimization)")
            return self._batch_process(fields_to_process)
        else:
            print(f"[LOG] Using sequential processing for {len(fields_to_process)} fields (O(N) legacy mode)")
            return self._sequential_process(fields_to_process)
    
    def _batch_process(self, fields_to_process):
        """
        O(1) batch processing: Extract all fields in a single API call.
        This dramatically reduces processing time from O(N) to O(1).
        """
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"
        
        # Build single prompt for all fields
        prompt = self.build_batch_prompt(fields_to_process)
        
        payload = {
            "model": "mistral",
            "prompt": prompt,
            "stream": False,
        }
        
        try:
            print("[LOG] Sending batch request to Ollama...")
            response = requests.post(ollama_url, json=payload)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Could not connect to Ollama at {ollama_url}. "
                "Please ensure Ollama is running and accessible."
            )
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Ollama returned an error: {e}")
        
        # Parse response
        json_data = response.json()
        raw_response = json_data["response"].strip()
        
        print("[LOG] Received batch response from Ollama")
        
        # Try to parse JSON response
        try:
            # Clean up response - remove markdown code blocks if present
            if "```json" in raw_response:
                raw_response = raw_response.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_response:
                raw_response = raw_response.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            extracted_data = json.loads(raw_response)
            
            # Process each field
            for field in fields_to_process:
                if field in extracted_data and extracted_data[field] is not None:
                    value = extracted_data[field]
                    # Handle None or empty values
                    if value == "" or value is None:
                        self.add_response_to_json(field, "-1")
                    else:
                        self.add_response_to_json(field, str(value))
                else:
                    # Field not found in response, set to -1
                    self.add_response_to_json(field, "-1")
            
            print("[LOG] Successfully parsed batch response")
            
        except json.JSONDecodeError as e:
            print(f"[WARNING] Failed to parse batch response as JSON: {e}")
            print(f"[WARNING] Raw response: {raw_response[:200]}...")
            print("[LOG] Falling back to sequential processing")
            # Fallback to sequential processing
            return self._sequential_process(fields_to_process)
        
        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")
        
        return self
    
    def _sequential_process(self, fields_to_process):
        """
        O(N) sequential processing: Extract each field with a separate API call.
        This is the legacy approach, kept for backward compatibility.
        """
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"
        
        for field in fields_to_process:
            prompt = self.build_prompt(field)
            
            payload = {
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
            }

            try:
                response = requests.post(ollama_url, json=payload)
                response.raise_for_status()
            except requests.exceptions.ConnectionError:
                raise ConnectionError(
                    f"Could not connect to Ollama at {ollama_url}. "
                    "Please ensure Ollama is running and accessible."
                )
            except requests.exceptions.HTTPError as e:
                raise RuntimeError(f"Ollama returned an error: {e}")

            # parse response
            json_data = response.json()
            parsed_response = json_data["response"]
            self.add_response_to_json(field, parsed_response)

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def add_response_to_json(self, field, value):
        """
        this method adds the following value under the specified field,
        or under a new field if the field doesn't exist, to the json dict
        """
        value = value.strip().replace('"', "")
        parsed_value = None

        if value != "-1":
            parsed_value = value

        if ";" in value:
            parsed_value = self.handle_plural_values(value)

        if field in self._json.keys():
            self._json[field].append(parsed_value)
        else:
            self._json[field] = parsed_value

        return

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

        print(
            f"\t[LOG]: Formating plural values for JSON, [For input {plural_value}]..."
        )
        values = plural_value.split(";")

        # Remove trailing leading whitespace
        for i in range(len(values)):
            current = i + 1
            if current < len(values):
                clean_value = values[current].lstrip()
                values[current] = clean_value

        print(f"\t[LOG]: Resulting formatted list of values: {values}")

        return values

    def get_data(self):
        return self._json
