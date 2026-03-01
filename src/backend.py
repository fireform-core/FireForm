import json
import os
import requests
from json_manager import JsonManager
from input_manager import InputManager
from pdfrw import PdfReader, PdfWriter

class textToJSON():
    def __init__(self, transcript_text, target_fields, json_data=None):
        # Initialize internal variables
        self.__transcript_text = transcript_text  # Raw string from transcription
        self.__target_fields = target_fields      # List of fields to extract
        self.__json = json_data if json_data is not None else {}
        
        # Validate input types before processing
        self.type_check_all()
        # Start the extraction process
        self.main_loop()

    def type_check_all(self):
        """ Validates that inputs are of the correct data type. """
        if not isinstance(self.__transcript_text, str):
            raise TypeError(f"ERROR in textToJSON() -> Transcript must be text. Received: {type(self.__transcript_text)}")
        if not isinstance(self.__target_fields, list):
            raise TypeError(f"ERROR in textToJSON() -> Target fields must be a list. Received: {type(self.__target_fields)}")

    def build_prompt(self, current_field):
        """ 
        Creates a structured prompt for the LLM to extract specific information.
        @params: current_field -> The specific JSON key the AI needs to find.
        """
        prompt = f""" 
            SYSTEM PROMPT:
            You are an AI assistant designed to help fill out JSON files with information extracted from transcribed voice recordings. 
            You will receive the transcription, and the name of the JSON field whose value you have to identify in the context. Return 
            only a single string containing the identified value for the JSON field. 
            If the field name is plural, and you identify more than one possible value in the text, return both separated by a ";".
            If you don't identify the value in the provided text, return "-1".
            ---
            DATA:
            Target JSON field to find in text: {current_field}
            
            TEXT: {self.__transcript_text}
            """
        return prompt

    def main_loop(self):
        """ Iterates through all target fields and requests data from the local LLM. """
        for field in self.__target_fields:
            prompt = self.build_prompt(field)
            
            # Configure Ollama URL (defaulting to localhost if env var is not set)
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
            ollama_url = f"{ollama_host}/api/generate"

            payload = {
                "model": "mistral",
                "prompt": prompt,
                "stream": False
            }

            try:
                response = requests.post(ollama_url, json=payload)
                response.raise_for_status()
                
                # Parse LLM response
                json_data = response.json()
                parsed_response = json_data['response']
                
                # Update the internal JSON dictionary with the new value
                self.add_response_to_json(field, parsed_response)
            except Exception as e:
                print(f"\t[ERROR]: Failed to get response for field '{field}': {e}")

        # Logging the final structured data
        print("----------------------------------")
        print("\t[LOG] Resulting JSON created from the input text:")
        print(json.dumps(self.__json, indent=2))
        print("--------- extracted data ---------")

    def add_response_to_json(self, field, value):
        """ 
        Safely adds a value to the JSON dictionary. 
        Converts existing entries to lists to handle multiple values for a single field.
        """
        # Clean the input value
        value = value.strip().replace('"', '')
        parsed_value = None

        # Set to None if value is missing (-1)
        if value != "-1":
            parsed_value = value 
        
        # Handle cases where the LLM returns multiple values separated by ';'
        if ";" in value:
            parsed_value = self.handle_plural_values(value)

        # Logic to prevent AttributeError: ensure field is always handled as a list
        if field in self.__json:
            if isinstance(self.__json[field], list):
                self.__json[field].append(parsed_value)
            else:
                # Convert existing string to list before appending
                self.__json[field] = [self.__json[field], parsed_value]
        else: 
            # Initialize as a list for consistency
            self.__json[field] = [parsed_value]

    def handle_plural_values(self, plural_value):
        """ Splits a string of values into a clean Python list. """
        if ";" not in plural_value:
            raise ValueError(f"Value is not plural: {plural_value}")
        
        print(f"\t[LOG]: Formatting plural values for JSON: {plural_value}")
        values = [v.strip() for v in plural_value.split(";")]
        print(f"\t[LOG]: Resulting list: {values}")
        
        return values

    def get_data(self):
        """ Returns the final extracted JSON dictionary. """
        return self.__json

class Fill():
    def __init__(self):
        pass
    
    @staticmethod
    def fill_form(user_input, definitions, pdf_form):
        """
        Fills a PDF form by mapping LLM-extracted data to form widgets.
        Includes logic to format lists into clean strings for PDF display.
        """
        output_pdf = pdf_form[:-4] + "_filled.pdf"

        # Process the input text and get structured JSON
        t2j = textToJSON(user_input, definitions)
        textbox_answers = t2j.get_data() 

        # Extract values as a list for ordered filling
        answers_list = list(textbox_answers.values())

        # Load the PDF template
        pdf = PdfReader(pdf_form)

        # Process each page in the PDF
        for page in pdf.pages:
            if page.Annots:
                # Sort annotations by position (top-to-bottom) to match field descriptions
                sorted_annots = sorted(
                    page.Annots,
                    key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )

                i = 0
                for annot in sorted_annots:
                    # Identify form fields (Widgets)
                    if annot.Subtype == '/Widget' and annot.T:
                        if i < len(answers_list):
                            current_val = answers_list[i]
                            
                            # CLEANING LOGIC: Convert lists to comma-separated strings
                            # This removes brackets [] and quotes '' from the PDF output
                            if isinstance(current_val, list):
                                clean_list = [str(v) for v in current_val if v is not None]
                                display_text = ", ".join(clean_list)
                            else:
                                display_text = str(current_val) if current_val is not None else ""

                            # Set the field value (V) and clear appearance (AP) for refresh
                            annot.V = f'{display_text}'
                            annot.AP = None
                            i += 1
                        else:
                            break 

        # Save the filled PDF
        PdfWriter().write(output_pdf, pdf)
        print(f"✅ Process Complete. Output saved to: {output_pdf}")
        
        return output_pdf