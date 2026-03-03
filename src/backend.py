import json
import os
import requests
from datetime import datetime
from fpdf import FPDF

class textToJSON():
    def __init__(self, transcript_text):
        """
        Initializes the extraction process using AI.
        """
        self.__transcript_text = transcript_text
        self.__json = {}
        
        if not isinstance(self.__transcript_text, str):
            raise TypeError(f"ERROR: Transcript must be text. Received: {type(self.__transcript_text)}")
        
        self.extract_dynamically()

    def build_dynamic_prompt(self):
        """ 
        UNIVERSAL DYNAMIC PROMPT:
        No specific names or incidents are mentioned here. 
        The AI must rely on logic to categorize information.
        """
        prompt = f""" 
            SYSTEM PROMPT:
            Analyze the provided text and convert it into a structured professional JSON report.
            
            CORE LOGIC:
            1. MANDATORY: Identify the "officer_name" (the person writing or lead on the report).
            2. CATEGORIZATION: Instead of long sentences, create specific keys for:
               - Locations , and people involved.
               - Actions performed (e.g., if help was given, use "assistance": "Yes").
               - Transfers or handovers (e.g., "recipient": "Name").
            3. FILTERING: Ignore filler phrases like "End of transmission", "Hello", or "Over".
            4. FORMAT: Use 'snake_case' for keys and 'Title Case' for values. 
            
            TEXT TO PROCESS:
            {self.__transcript_text}
            """
        return prompt

    def extract_dynamically(self):
        """ Calls the LLM and performs deep cleaning of the data. """
        prompt = self.build_dynamic_prompt()
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        
        payload = {
            "model": "mistral",
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }

        try:
            response = requests.post(f"{ollama_host}/api/generate", json=payload)
            response.raise_for_status()
            raw_data = json.loads(response.json()['response'])
            
            # Post-processing cleanup
            cleaned_data = {}
            for key, value in raw_data.items():
                if value and value != "" and value != "-1":
                    if isinstance(value, str):
                        cleaned_data[key] = value.replace('_', ' ').title()
                    elif isinstance(value, list):
                        cleaned_data[key] = [v.replace('_', ' ').title() if isinstance(v, str) else v for v in value]
                    else:
                        cleaned_data[key] = value
            
            self.__json = cleaned_data
            
        except Exception as e:
            print(f"\t[ERROR] AI Extraction failed: {e}")
            self.__json = {"error": "Failed to analyze text"}

    def get_data(self):
        return self.__json

class DynamicPDFGenerator(FPDF):
    """ Generates a professional PDF with automated metadata and smart signature line. """
    
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.set_text_color(44, 62, 80)
        self.cell(0, 15, 'DYNAMIC INTELLIGENCE REPORT', ln=True, align='C')
        self.line(10, 25, 200, 25)
        self.ln(5)

    def generate(self, data, output_path, input_file_path):
        """ Dynamically builds the PDF content from the JSON data. """
        self.add_page()
        
        # 1. Automatic Timestamp
        try:
            mod_time = os.path.getmtime(input_file_path)
            report_date = datetime.fromtimestamp(mod_time).strftime('%d/%m/%Y %H:%M')
        except:
            report_date = datetime.now().strftime('%d/%m/%Y %H:%M')

        self.set_font("Arial", "I", 10)
        self.cell(0, 10, f"Report generated on: {report_date}", ln=True, align='R')
        self.ln(5)

        # 2. Main Body (Iterating through JSON)
        for key, value in data.items():
            # Section Title
            self.set_font("Arial", "B", 11)
            self.set_fill_color(240, 240, 240)
            label = key.replace('_', ' ').upper()
            self.cell(0, 8, f" {label}", ln=True, fill=True)
            
            self.set_font("Arial", "", 12)
            self.set_text_color(0, 0, 0)
            
            # Logic to handle strings, lists, or nested dicts
            if isinstance(value, list):
                for item in value:
                    self.set_x(15)
                    text_item = " ".join([str(v) for v in item.values()]) if isinstance(item, dict) else str(item)
                    self.multi_cell(0, 8, f" - {text_item}")
            else:
                self.set_x(15)
                text_value = " ".join([str(v) for v in value.values()]) if isinstance(value, dict) else str(value)
                self.multi_cell(0, 10, text_value)
            self.ln(3)

        # 3. Smart Signature Block
        self.ln(15)
        # We look for officer_name to place the final signature
        signer_name = data.get('officer_name', 'Authorized Declarant')

        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "Signature:", ln=True)
        
        self.set_font("Times", "I", 16) 
        self.set_text_color(20, 40, 160) 
        self.cell(0, 10, f"      {signer_name}", ln=True)

        self.output(output_path)
        print(f"✅ Success: PDF report saved at '{output_path}'")

class Fill():
    @staticmethod
    def fill_form(user_input, input_path, output_filename="dynamic_report.pdf"):
        """
        Main entry point. Coordinates extraction, JSON export, and PDF generation.
        """
        # Step 1: Extract data
        t2j = textToJSON(user_input)
        extracted_data = t2j.get_data()

        # Step 2: Export Raw JSON
        json_output_path = output_filename.replace(".pdf", ".json")
        try:
            with open(json_output_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, indent=4, ensure_ascii=False)
            print(f"✅ Success: Data exported to '{json_output_path}'")
        except Exception as e:
            print(f"⚠️ Warning: JSON export failed: {e}")

        # Step 3: Generate PDF
        pdf_gen = DynamicPDFGenerator()
        pdf_gen.generate(extracted_data, output_filename, input_path)
        
        return output_filename