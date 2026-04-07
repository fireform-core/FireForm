import json
import os
import requests


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json=None):
        if json is None:
            json = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields  # List, contains the template field.
        self._json = json  # dictionary

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

    def main_loop(self):
        # self.type_check_all()
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        # 1. CHANGE ENDPOINT: Switch from /api/generate to /api/chat
        ollama_url = f"{ollama_host}/api/chat"

        # 2. CACHE THE CONTEXT: Build the heavy system message ONCE before the loop
        system_message = {
            "role": "system",
            "content": f"""You are an AI data extraction assistant. You extract information from transcribed voice recordings to fill out a JSON file. 
Return ONLY a single string containing the extracted value.
If the field implies plural values and you find multiple, separate them with a ";".
If you cannot find the value in the text, return exactly "-1". Do not add any conversational filler or markdown.

TRANSCRIPTION TEXT:
{self._transcript_text}"""
        }

        # 3. FIX THE LIST BUG: Iterate directly over the list (removed .keys())
        for field in self._target_fields:
            
            # 4. LIGHTWEIGHT QUERY: Only ask for the specific field in the loop
            user_message = {
                "role": "user",
                "content": f"Target JSON field to extract: {field}"
            }

            payload = {
                "model": "mistral",
                "messages": [system_message, user_message], # Pass as a conversation
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

            # 5. PARSE CHAT RESPONSE: Chat API returns data in message['content']
            json_data = response.json()
            parsed_response = json_data["message"]["content"]
            
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
