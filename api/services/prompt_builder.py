def build_extraction_prompt(input_text: str) -> str:
    return f"""
You are an AI system that extracts structured information from incident reports.

Extract the following fields:
- name
- location
- date (YYYY-MM-DD if possible)
- incident_type
- description

Return ONLY valid JSON. Do not include any extra text.

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

Now extract from:

{input_text}
"""