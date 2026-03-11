import os
from src.filler import Filler
from src.llm import LLM
from src.profiles import ProfileLoader
from commonforms import prepare_form


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        self.llm = LLM()

    def create_template(self, pdf_path: str):
        """
        By using commonforms, we create an editable .pdf template and we store it.
        """
        template_path = pdf_path[:-4] + "_template.pdf"
        prepare_form(pdf_path, template_path)
        return template_path

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str, profile_name: str = None, use_batch_processing: bool = True):
        """
        It receives the raw data, runs the PDF filling logic,
        and returns the path to the newly created file.
        
        Args:
            user_input: The transcript text to extract information from
            fields: List or dict of field definitions
            pdf_form_path: Path to the PDF template
            profile_name: Optional department profile name (e.g., 'fire_department')
            use_batch_processing: Whether to use O(1) batch processing (default: True)
        """
        print("[1] Received request from frontend.")
        print(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            print(f"Error: PDF template not found at {pdf_form_path}")
            return None  # Or raise an exception

        # If a profile is specified, use human-readable labels
        if profile_name:
            print(f"[3] Using department profile: {profile_name}")
            try:
                profile_mapping = ProfileLoader.get_field_mapping(profile_name)
                print(f"[4] Loaded {len(profile_mapping)} field mappings from profile")
                
                # Use profile labels for LLM extraction
                self.llm._target_fields = profile_mapping
                self.llm._use_profile_labels = True
            except FileNotFoundError as e:
                print(f"Warning: {e}")
                print("Falling back to standard field extraction")
                self.llm._target_fields = fields
                self.llm._use_profile_labels = False
        else:
            print("[3] No profile specified, using standard field extraction")
            self.llm._target_fields = fields
            self.llm._use_profile_labels = False

        # Set batch processing mode
        self.llm._use_batch_processing = use_batch_processing
        
        print("[5] Starting extraction and PDF filling process...")
        try:
            self.llm._transcript_text = user_input
            output_name = self.filler.fill_form(pdf_form=pdf_form_path, llm=self.llm)

            print("\n----------------------------------")
            print("✅ Process Complete.")
            print(f"Output saved to: {output_name}")

            return output_name

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            # Re-raise the exception so the frontend can handle it
            raise e
