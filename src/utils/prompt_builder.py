class PromptBuilder:
    @staticmethod
    def build_extraction_prompt(user_input: str, fields: list):
        field_list = ", ".join(fields)

        prompt = f"""
You are an incident report extraction assistant.

Extract the following fields strictly in JSON format:
{field_list}

Rules:
- Return only valid JSON
- Do not include explanations
- Missing fields should be empty strings
- Keep keys exactly as provided

Incident description:
{user_input}

Expected format:
{{
    "location": "",
    "time": "",
    "severity": "",
    "description": ""
}}
"""
        return prompt