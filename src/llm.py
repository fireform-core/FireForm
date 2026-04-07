from api.schemas.report_class import CanonicalSchema, CanonicalFieldEntry
from api.db.models import Datatype
from typing import Any
import json
import os
import requests
from dotenv import load_dotenv
load_dotenv()


class LLM:
    model_config = None

    def __init__(self, transcript_text=None, target_fields=None, json=None):
        if json is None:
            json = {}
        self._transcript_text = transcript_text  # str
        self._target_fields = target_fields  # List, contains the template field.
        self._json = json  # dictionary

        if LLM.model_config is None:
            LLM.set_model_config()

    @classmethod
    def set_model_config(cls, provider: str = None, model_name: str = None):
        """
        Configure the model settings for local or online inference globally for the class.
        Falls back to environment variables LLM_PROVIDER and LLM_MODEL if not specified.
        """
        provider = provider or os.getenv("LLM_PROVIDER", "ollama")
        model_name = model_name or os.getenv("LLM_MODEL", "mistral")

        config = {
            "provider": provider,
            "model": model_name
        }

        if provider == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            config["url"] = f"{host}/api/chat"
        elif provider == "gemini":
            config["url"] = "https://generativelanguage.googleapis.com/v1beta/models"
            config["api_key"] = os.getenv("GEMINI_API_KEY")
        else:
            raise ValueError(f"Unknown provider: {provider}")

        cls.model_config = config

    @classmethod
    def inference(cls, messages: list[dict], format: str = "json") -> str:
        """
        Run inference using the globally specified configuration. Returns the raw string response content.
        """
        if cls.model_config is None:
            cls.set_model_config()

        config = cls.model_config
        provider = config.get("provider", "ollama")
        model = config.get("model", "mistral")
        url = config.get("url")

        if provider == "ollama":
            payload = {
                "model": model,
                "messages": messages,
                "stream": False
            }
            if format == "json":
                payload["format"] = "json"

            response = requests.post(url, json=payload)
            response.raise_for_status()
            return response.json()["message"]["content"]

        elif provider == "gemini":
            api_key = config.get("api_key")
            if not api_key:
                raise ValueError("Gemini API key not found in GEMINI_API_KEY")

            gemini_contents = []
            system_instruction = None

            for msg in messages:
                role = msg["role"]
                content = msg["content"]

                if role == "system":
                    system_instruction = content
                    continue

                gemini_role = "model" if role == "assistant" else "user"
                gemini_contents.append({
                    "role": gemini_role,
                    "parts": [{"text": content}]
                })

            payload = {"contents": gemini_contents}

            if system_instruction:
                payload["system_instruction"] = {
                    "parts": [{"text": system_instruction}]
                }

            if format == "json":
                payload["generationConfig"] = {
                    "responseMimeType": "application/json"
                }

            gemini_url = f"{url}/{model}:generateContent?key={api_key}"
            response = requests.post(gemini_url, json=payload)
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]

        else:
            raise ValueError(f"Unknown provider: {provider}")

    @staticmethod
    def syntactic_validator(expected_schema: CanonicalFieldEntry, extracted_value: Any) -> list[dict]:
        """
        A validator to validate the syntactic correctness of extracted values against Canonical Field Descriptors
        """
        errors = []

        if expected_schema.data_type == Datatype.INT:
            try:
                int(extracted_value)
            except (ValueError, TypeError):
                errors.append({"data_type_error": f"expected: int, however {extracted_value} is: {type(extracted_value).__name__}"})
        elif expected_schema.data_type == Datatype.STRING:
            if not isinstance(extracted_value, str):
                errors.append({"data_type_error": f"expected: string, however {extracted_value} is: {type(extracted_value).__name__}"})
        elif expected_schema.data_type == Datatype.DATE:
            if not isinstance(extracted_value, str):
                errors.append({"data_type_error": f"expected: date string, however {extracted_value} is: {type(extracted_value).__name__}"})

        if expected_schema.word_limit and isinstance(extracted_value, str) and len(extracted_value.split(" ")) > expected_schema.word_limit:
            errors.append({"word_limit_error": f"extracted value word count {len(extracted_value.split(' '))} exceeds word limit of {expected_schema.word_limit}"})

        if expected_schema.allowed_values and "values" in expected_schema.allowed_values:
            allowed = expected_schema.allowed_values["values"]
            if extracted_value not in allowed:
                errors.append({"allowed_values_error": f"extracted value: {extracted_value} not in allowed values: {allowed}"})

        return errors if errors else None

    @classmethod
    def semantic_validator(cls, extraction_batch: list[dict], context: str) -> dict:
        """
        A validator to validate the semantic correctness of a batch of extracted values against the original context and reasoning.
        extraction_batch: list of dicts with: field_name, description, extracted_value, reasoning.
        Returns: dict mapping field_name to a string of semantic errors. Empty if valid.
        """
        if not extraction_batch:
            return {}

        prompt = f"""
            You are a semantic validator agent. Your task is to verify if the extracted values make semantic sense 
            based on the provided source text, field descriptions, and the reasoning used for extraction.

            Batch of Extracted Fields:
            {json.dumps(extraction_batch, indent=2)}
            
            Source Text:
            {context}

            Given the source text, evaluate if each extracted value in the batch is correct and semantically sound according to its field description?
            Respond in JSON format as a mapping of field_name to validation results. Each validation result must contain "is_valid" (boolean) and "errors" (a string explaining why it is invalid, or empty string if valid).
            
            Example output:
            {{
                "field_name_1": {{
                    "is_valid": false,
                    "errors": "The extracted value mentions a date, but the field description asks for a status."
                }},
                "field_name_2": {{
                    "is_valid": true,
                    "errors": ""
                }}
            }}
        """

        messages = [{"role": "user", "content": prompt}]

        try:
            response_content = cls.inference(messages, format="json")
            parsed = json.loads(response_content)

            errors_dict = {}
            for field_name, result in parsed.items():
                if isinstance(result, dict) and not result.get("is_valid", True):
                    errors_dict[field_name] = result.get("errors", "Semantic validation failed")
            return errors_dict
        except Exception as e:
            return {item["field_name"]: f"Failed to perform semantic validation: {e}" for item in extraction_batch}

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
        # self.type_check_all()
        for field in self._target_fields.keys():
            prompt = self.build_prompt(field)

            try:
                parsed_response = self.inference(messages=[{"role": "user", "content": prompt}], format=None)
            except Exception as e:
                raise RuntimeError(f"Ollama/Inference returned an error: {e}")

            self.add_response_to_json(field, parsed_response)

        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self._json, indent=2))
        print("--------- extracted data ---------")

        return self

    def extractor(self, extraction_target: CanonicalSchema):
        """
        An extractor agent that extracts target values from the trasncript, and performs basic syntactic validation of the
        extracted values, and iteratively redoes extraction for failed fields
        """
        MAX_OUTER_RETRIES = 10
        MAX_SYNTACTIC_RETRIES = 5

        pending_fields = {field.canonical_name: field for field in extraction_target.canonical_fields}
        results_dict = {}
        semantic_errors = {}

        # Init conversation history array
        conversation_history = [
            {
                "role": "system",
                "content": "You are a report generator agent. You extract objectives from source text into a JSON map with `candidate_value`, `reasoning`, and `confidence`."
            }
        ]

        outer_iteration = 0
        while pending_fields:
            outer_iteration += 1

            if outer_iteration > MAX_OUTER_RETRIES:
                for field_name in list(pending_fields.keys()):
                    results_dict[field_name] = None
                break

            target_fields_info = []
            for field_name, field in pending_fields.items():
                field_info = {
                    "field_name": field.canonical_name,
                    "description": field.description,
                    "expected_data_type": field.data_type,
                    "word_limit": field.word_limit if field.data_type == "string" else None,
                    "required": field.required,
                    "allowed_values": field.allowed_values,
                }
                target_fields_info.append(field_info)

            prompt = f"""
            Extract ONLY the specified target fields from the source text. 
            Respond in the requested JSON format.

            Target Fields: {target_fields_info}
            Source Text: {self._transcript_text}

            JSON Format Expectation:
            {{
                "field_name_1": {{
                    "candidate_value": <Extracted value that fits requirements>,
                    "reasoning": <reasoning>,
                    "confidence": <confidence between 0 and 1>
                }}
            }}
            """

            conversation_history.append({"role": "user", "content": prompt})

            try:
                response_content = self.inference(conversation_history, format="json")
                conversation_history.append({"role": "assistant", "content": response_content})
                parsed_response = json.loads(response_content)
            except Exception as e:
                parsed_response = {}

            syntactically_valid = {}
            fields_to_fix = {}

            # Initial syntactic validation
            for field_name in list(pending_fields.keys()):
                if field_name not in parsed_response:
                    fields_to_fix[field_name] = {
                        "extractor_output": None,
                        "errors": [{"missing_field": "Field was not extracted."}]
                    }
                    continue

                list_or_dict = parsed_response[field_name]
                if not isinstance(list_or_dict, dict):
                    fields_to_fix[field_name] = {
                        "extractor_output": list_or_dict,
                        "errors": [{"format_error": "Extracted field output must be a dictionary with candidate_value."}]
                    }
                    continue

                candidate_value = list_or_dict.get("candidate_value")
                errors = self.syntactic_validator(pending_fields[field_name], candidate_value)

                if errors:
                    fields_to_fix[field_name] = {
                        "extractor_output": list_or_dict,
                        "errors": errors
                    }
                else:
                    syntactically_valid[field_name] = list_or_dict

            # 2. Syntactic Correction Loop
            syntactic_retry = 0
            while fields_to_fix:
                syntactic_retry += 1

                if syntactic_retry > MAX_SYNTACTIC_RETRIES:
                    for field_name in list(fields_to_fix.keys()):
                        syntactically_valid[field_name] = fields_to_fix[field_name].get("extractor_output") or {"candidate_value": None, "reasoning": "max retries", "confidence": 0}
                    break

                correction_targets = []
                for field_name, fix_ctx in fields_to_fix.items():
                    field_info = {
                        "field_name": field_name,
                        "expected_data_type": pending_fields[field_name].data_type,
                        "previous_invalid_output": fix_ctx.get("extractor_output"),
                        "syntactic_errors": fix_ctx.get("errors")
                    }
                    correction_targets.append(field_info)

                correction_prompt = f"""
                You previously extracted values that failed syntactic validation.
                Please re-extract ONLY the following fields, correcting the syntactic errors indicated.
                Return the exact same JSON format.

                Target Fields to Correct:
                {correction_targets}
                """

                conversation_history.append({"role": "user", "content": correction_prompt})

                try:
                    response_content = self.inference(conversation_history, format="json")
                    conversation_history.append({"role": "assistant", "content": response_content})
                    correction_response = json.loads(response_content)
                except Exception as e:
                    correction_response = {}

                new_fields_to_fix = {}
                for field_name, fix_ctx in fields_to_fix.items():
                    if field_name in correction_response and isinstance(correction_response[field_name], dict):
                        candidate_value = correction_response[field_name].get("candidate_value")
                        errors = self.syntactic_validator(pending_fields[field_name], candidate_value)
                        if errors:
                            new_fields_to_fix[field_name] = {
                                "extractor_output": correction_response[field_name],
                                "errors": errors
                            }
                        else:
                            syntactically_valid[field_name] = correction_response[field_name]
                    else:
                        new_fields_to_fix[field_name] = fix_ctx

                fields_to_fix = new_fields_to_fix

            # 3. Semantic Validation Loop (Batch and Threshold Filtering)
            batch_to_validate = []

            for field_name, extracted_dict in syntactically_valid.items():
                if not isinstance(extracted_dict, dict):
                    extracted_dict = {"candidate_value": None, "confidence": 0}
                confidence = extracted_dict.get("confidence", 0)
                try:
                    confidence = float(confidence)
                except (ValueError, TypeError):
                    confidence = 0.0

                if confidence >= 0.90:
                    results_dict[field_name] = extracted_dict.get("candidate_value")
                    del pending_fields[field_name]
                else:
                    batch_to_validate.append({
                        "field_name": field_name,
                        "description": pending_fields[field_name].description,
                        "extracted_value": extracted_dict.get("candidate_value"),
                        "reasoning": extracted_dict.get("reasoning", "")
                    })

            if batch_to_validate:
                batch_errors = self.semantic_validator(batch_to_validate, self._transcript_text)

                failed_semantic_names = []
                for item in batch_to_validate:
                    f_name = item["field_name"]
                    if f_name in batch_errors:
                        semantic_errors[f_name] = batch_errors[f_name]
                        failed_semantic_names.append(f_name)
                    else:
                        results_dict[f_name] = item["extracted_value"]
                        del pending_fields[f_name]

                if failed_semantic_names:
                    feedback_msg = "The following fields failed semantic validation. Please correct your reasoning and re-extract them accurately based on the source text:\n"
                    for f_name in failed_semantic_names:
                        feedback_msg += f"- '{f_name}': {semantic_errors[f_name]}\n"
                    conversation_history.append({"role": "user", "content": feedback_msg})

            # 4. End of iteration. If pending_fields is empty, loop breaks.

        # Store results for existing class dependencies
        for field, value in results_dict.items():
            self.add_response_to_json(field, str(value))

        return results_dict

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
