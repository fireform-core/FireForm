import datetime
import hashlib
import json
import logging
import os
import signal
import sys
import time
import requests

logger = logging.getLogger(__name__)

#folder for checkpoint files
#default is /tmp/fireform_states, can override using FIREFORM_STATE_DIR env variable
STATE_DIR = os.getenv("FIREFORM_STATE_DIR", "/tmp/fireform_states")

#max # tries for an Ollama timeout
MAX_RETRIES = 3


class LLM:
    def __init__(self, transcript_text=None, target_fields=None, json_data=None):
        if json_data is None:
            json_data = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields       # dict (pypdf) or list
        self._json = json_data                    # dictionary

        #LLM() is created first, _transcript_test/_target_fields created afterwards,
        #so session ID must be computed later in _setup_checkpoint(), called by main_loop()
        self._session_id = None
        self._state_file = None

    #type checking
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

    #checkpoint setup helpers
    def _get_field_names(self):
        """
        Return field names as a list regardless of whether
        _target_fields is a dict or a list. 
        """
        if self._target_fields is None:
            return []
        if isinstance(self._target_fields, dict):
            return list(self._target_fields.keys())
        return list(self._target_fields)

    def _setup_checkpoint(self):
        """
        Compute the session_id and state_file path from 
        _transcript_text and _target_fields. Called at the top of
        main_loop().

        Hashing transcript and field names means the same transcript
        run through different form templates will produce two separate checkpoint files.
        """
        field_names = self._get_field_names()
        fingerprint = (self._transcript_text or "") + str(sorted(field_names))
        self._session_id = hashlib.md5(fingerprint.encode()).hexdigest()
        os.makedirs(STATE_DIR, exist_ok=True)
        self._state_file = os.path.join(
            STATE_DIR, f".fireform_state_{self._session_id}.json"
        )

    #signal handling
    def _handle_interrupt(self, signum, frame):
        """On Ctrl+C, flush checkpoint before exit."""
        logger.warning(
            "\n[FireForm] Interrupted! Saving checkpoint so you can resume later..."
        )
        self.save_state()
        sys.exit(1)

    #checkpoint handling
    def load_state(self) -> bool:
        """
        Load a previously saved checkpoint, returning true
        if a checkpoint was found and loaded. False otherwise.
        """
        if not os.path.exists(self._state_file):
            return False

        try:
            with open(self._state_file, "r") as f:
                loaded = json.load(f)
            self._json = loaded
            already_done = [k for k, v in self._json.items() if v is not None]
            print(
                f"\t[LOG] Found existing state file. Resuming session "
                f"{self._session_id[:8]}... "
                f"({len(already_done)} field(s) already extracted: {already_done})"
            )
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"[FireForm] State file found but unreadable ({e}). Starting fresh."
            )
            self._json = {}
            return False

    def save_state(self):
        """
        Writes to a .tmp file first then renames, so a crash mid-write
        won't corrupts the checkpoint.
        """
        if not self._state_file:
            return  # called before _setup_checkpoint, no write
        tmp_path = self._state_file + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(self._json, f, indent=2)
            os.replace(tmp_path, self._state_file) 
        except OSError as e:
            logger.error(f"[FireForm] Failed to save checkpoint: {e}")

    def clear_state(self):
        """Remove the checkpoint file after successful completion."""
        if self._state_file and os.path.exists(self._state_file):
            try:
                os.remove(self._state_file)
                print("\t[LOG] Checkpoint cleared after successful completion.")
            except OSError as e:
                logger.warning(f"[FireForm] Could not remove checkpoint: {e}")

    #error logging
    def _log_extraction_error(self, field: str, raw_response: str, reason: str):
        """
        Append a failed field extraction event to a JSONL error log.
        """
        log_dir = os.getenv("FIREFORM_LOG_DIR", STATE_DIR)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "extraction_errors.jsonl")
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "session_id": self._session_id,
            "field": field,
            "raw_response": raw_response[:300],
            "reason": reason,
        }
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass 

    #prompt building
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

    #main
    def main_loop(self):
        self._setup_checkpoint()

        #register Ctrl+C handler
        signal.signal(signal.SIGINT, self._handle_interrupt)

        #load existing checkpoints
        self.load_state()

        #determine which fields stil need extraction
        all_field_names = self._get_field_names()
        fields_to_process = [f for f in all_field_names if f not in self._json]

        skipped = len(all_field_names) - len(fields_to_process)
        if skipped:
            print(
                f"\t[LOG] Skipping {skipped} already-extracted field(s). "
                f"{len(fields_to_process)} remaining."
            )

        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_host}/api/generate"

        for field in fields_to_process:
            prompt = self.build_prompt(field)
            payload = {
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
            }

            #retry loop
            response = None
            for attempt in range(MAX_RETRIES):
                try:
                    response = requests.post(ollama_url, json=payload, timeout=120)
                    response.raise_for_status()
                    break  # success

                except requests.exceptions.Timeout:
                    if attempt < MAX_RETRIES - 1:
                        wait = 5.0 * (attempt + 1)
                        logger.warning(
                            f"[FireForm] Ollama timed out on '{field}' "
                            f"(attempt {attempt + 1}/{MAX_RETRIES}). "
                            f"Retrying in {wait:.0f}s..."
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            f"[FireForm] All {MAX_RETRIES} retries failed for "
                            f"'{field}'. Saving checkpoint."
                        )
                        self.save_state()
                        raise

                except requests.exceptions.ConnectionError:
                    self.save_state()
                    raise ConnectionError(
                        f"Could not connect to Ollama at {ollama_url}. "
                        "Please ensure Ollama is running and accessible."
                    )

                except requests.exceptions.HTTPError as e:
                    raise RuntimeError(f"Ollama returned an error: {e}")

            json_data = response.json()
            parsed_response = json_data["response"]

            #Ollama value not found
            if parsed_response.strip() == "-1":
                self._log_extraction_error(
                    field, parsed_response,
                    "model returned -1 (value not found in transcript)"
                )

            self.add_response_to_json(field, parsed_response)
            self.save_state()  # checkpoint after every successful field

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        self.clear_state()
        return self

    #json helpers
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