import os
from src.filler import Filler
from src.llm import LLM
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

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
        """
        It receives the raw data, runs the PDF filling logic,
        and returns the path to the newly created file.
        """
        print("[1] Received request from frontend.")
        print(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            print(f"Error: PDF template not found at {pdf_form_path}")
            return None  # Or raise an exception

        print("[3] Starting extraction and PDF filling process...")
        try:
            # Add implicit Location Summary field to extract for Geotagging (Issue #108)
            mapping_fields = {f: None for f in fields}
            mapping_fields["Location Summary"] = None
            
            self.llm._target_fields = mapping_fields
            self.llm._transcript_text = user_input
            
            # The filler fills the PDF based on the LLM's final state
            # It will ignore "Location Summary" if the PDF doesn't have a matching visual field index,
            # but we can intercept it here for map generation.
            self.llm.main_loop()
            
            extracted_data = self.llm.get_data()
            location_text = extracted_data.get("Location Summary")
            
            map_image_path = None
            if location_text and location_text != "-1":
                from src.geocoder import Geotagger
                geotagger = Geotagger()
                coords = geotagger.get_coordinates(location_text)
                if coords:
                    lat, lon = coords
                    map_image_path = geotagger.generate_map_image(lat, lon)
            
            output_name = self.filler.fill_form(pdf_form=pdf_form_path, llm=self.llm, map_image_path=map_image_path)

            print("\n----------------------------------")
            print("✅ Process Complete.")
            print(f"Output saved to: {output_name}")

            return output_name

        except Exception as e:
            print(f"An error occurred during PDF generation: {e}")
            # Re-raise the exception so the frontend can handle it
            raise e
