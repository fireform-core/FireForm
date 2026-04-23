import os
from src.filler import Filler
from src.llm import LLM


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def create_template(self, pdf_path: str):
        """
        By using commonforms, we create an editable .pdf template and we store it.
        """
        # Lazy import
        from commonforms import prepare_form
        template_path = pdf_path[:-4] + "_template.pdf"

        os.system("taskkill /F /IM ollama.exe >nul 2>&1")
        print("Cleared existing Ollama instances. Starting fresh...")
        
        
        prepare_form(pdf_path, template_path)
        return template_path

    def _required_fields(self, fields: dict) -> list[str]:
        required = []
        for field_name, metadata in fields.items():
            if isinstance(metadata, dict):
                if metadata.get("required", True):
                    required.append(field_name)
            else:
                required.append(field_name)
        return required

    def _is_missing_value(self, value) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            clean = value.strip()
            return clean == "" or clean == "-1"
        if isinstance(value, list):
            return len(value) == 0
        return False

    def _merge_valid_data(self, base_data: dict, extracted_data: dict) -> dict:
        merged = dict(base_data)
        for field, extracted_value in extracted_data.items():
            if not self._is_missing_value(extracted_value):
                merged[field] = extracted_value
            elif field not in merged:
                merged[field] = None
        return merged

    def _compute_required_progress(self, data: dict, required_fields: list[str]):
        if not required_fields:
            return 100, [], []

        completed = []
        missing = []
        for field in required_fields:
            if self._is_missing_value(data.get(field)):
                missing.append(field)
            else:
                completed.append(field)

        completion_pct = int((len(completed) / len(required_fields)) * 100)
        return completion_pct, completed, missing

    def fill_form(
        self,
        user_input: str,
        fields: dict,
        pdf_form_path: str,
        retry_input_texts: list[str] | None = None,
        max_retry_rounds: int = 1,
    ):
        """
        It receives the raw data, runs the PDF filling logic,
        and returns the path to the newly created file.
        """
        print("[1] Received request from frontend.")
        print(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            print(f"Error: PDF template not found at {pdf_form_path}")
            raise FileNotFoundError(f"PDF template not found at {pdf_form_path}")

        print("[3] Starting extraction and PDF filling process...")
        try:
            required_fields = self._required_fields(fields)
            all_round_texts = [user_input]
            if retry_input_texts:
                all_round_texts.extend(retry_input_texts)

            extra_auto_rounds = max(0, max_retry_rounds)
            collected_data = {}
            latest_progress = {
                "required_completion_pct": 0,
                "completed_required_fields": [],
                "missing_required_fields": required_fields,
            }

            attempts_used = 0
            round_index = 0

            while True:
                if round_index < len(all_round_texts):
                    current_text = all_round_texts[round_index]
                elif extra_auto_rounds > 0:
                    current_text = all_round_texts[-1]
                    extra_auto_rounds -= 1
                else:
                    break

                attempts_used += 1
                self.llm._target_fields = fields
                self.llm._transcript_text = current_text

                partial_round_data = {}

                def progress_callback(field, parsed_response, _index, _total):
                    nonlocal partial_round_data, collected_data, latest_progress
                    partial_round_data = dict(self.llm.get_data())
                    tentative_data = self._merge_valid_data(collected_data, partial_round_data)
                    completion_pct, completed, missing = self._compute_required_progress(
                        tentative_data, required_fields
                    )
                    latest_progress = {
                        "required_completion_pct": completion_pct,
                        "completed_required_fields": completed,
                        "missing_required_fields": missing,
                    }

                self.llm.main_loop(progress_callback=progress_callback, reset_json=True)

                collected_data = self._merge_valid_data(collected_data, partial_round_data)
                completion_pct, completed, missing = self._compute_required_progress(
                    collected_data, required_fields
                )
                latest_progress = {
                    "required_completion_pct": completion_pct,
                    "completed_required_fields": completed,
                    "missing_required_fields": missing,
                }

                if not missing:
                    break

                round_index += 1

            output_name = None
            status = "incomplete"
            if not latest_progress["missing_required_fields"]:
                output_name = self.filler.fill_form_with_answers(
                    pdf_form=pdf_form_path,
                    answers=collected_data,
                )
                status = "completed"

            retry_prompt = None
            if latest_progress["missing_required_fields"]:
                missing_joined = ", ".join(latest_progress["missing_required_fields"])
                retry_prompt = (
                    "Some required information is still missing. "
                    f"Please answer these fields: {missing_joined}."
                )

            print("\n----------------------------------")
            print("✅ Process Complete.")
            print(f"Output saved to: {output_name}")

            return {
                "output_pdf_path": output_name,
                "status": status,
                "required_completion_pct": latest_progress["required_completion_pct"],
                "completed_required_fields": latest_progress["completed_required_fields"],
                "missing_required_fields": latest_progress["missing_required_fields"],
                "attempts_used": attempts_used,
                "retry_prompt": retry_prompt,
            }

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            # Re-raise the exception so the frontend can handle it
            raise e
