def build_extraction_prompt(input_text: str) -> str:
    return f"""
You are an AI system that extracts structured information from incident reports.
Your task is to extract ONLY information explicitly present in the input text.

STRICT RULES:
- Do NOT infer or guess missing information
- If a field is not clearly mentioned, return an empty string ""
- Do NOT add any extra fields beyond those specified
- Do NOT modify or reinterpret values 

Extract the following fields:
- name
- location
- date (YYYY-MM-DD if possible)
- incident_type
- description

Return ONLY valid JSON. Do not include any extra text, explanation, or formatting outside JSON.
The output MUST be a valid JSON object and parsable by json.loads().
Format:
{{
  "name": "",
  "location": "",
  "date": "",
  "incident_type": "",
  "description": ""
}}

Example:

Input:
Fire reported near Central Park on Jan 5 involving a vehicle.

Output:
{{
  "name": "",
  "location": "Central Park",
  "date": "2024-01-05",
  "incident_type": "fire",
  "description": "Fire involving a vehicle"
}}

Negative Example (DO NOT DO THIS):

Incorrect Output:
(This output is incorrect because it includes inferred/assumed values)
{{
  "location": "Central Park (assumed)",
  "date": "2024-01-05"
}}

Correct Output:
{{
  "location": "Central Park",
  "date": ""
}}

Now extract strictly from the following input (follow all rules above):

{input_text}
"""

def build_field_prompt(transcript_text: str, current_field: str) -> str:
    return f"""
SYSTEM PROMPT:
You are an AI assistant designed to help fill out JSON fields with information extracted from transcribed text.

You will receive:
- a transcript
- a target field name

Return ONLY the value for that field.

Rules:
- If multiple values exist → separate with ";"
- If no value found → return "-1"
- Do NOT add explanation

DATA:
Target JSON field: {current_field}

TEXT:
{transcript_text}
"""