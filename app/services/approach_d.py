import json
from collections.abc import Iterable, Mapping
from pathlib import Path
import requests
from pdfrw import PdfName, PdfReader, PdfWriter

class ApproachD:
    def __init__(self):
        pass

    @staticmethod
    def fill_form(narrative: str, target_json: str, pdf_path: str, output_pdf_path: str):
        prompt = """
        You are a precise data extraction engine. Extract information from the provided incident narrative and format it as a valid JSON object strictly adhering to the specified JSON Schema structure and field types. Do not include introductory text, explanations, or Markdown boilerplate—return ONLY the raw JSON object.
        User Prompt:
        Read the following incident narrative and complete the JSON object based on the given target schema.
        Story:
        """

        whole_prompt = prompt + narrative + "\nTarget JSON Schema:\nJSON\n" + target_json

        payload = {
            "model": "qwen2.5:1.5b",
            "prompt": whole_prompt,
            "format": "json",
            "stream": False,
        }

        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
        response.raise_for_status()

        json_data = response.json() 

        response_str = json_data.get("response", "{}")
        # print("LLM Response:\n", response_str)

        if "```json" in response_str:
            response_str = response_str.split("```json")[1].split("```")[0].strip()
        elif "```" in response_str:
            response_str = response_str.split("```")[1].split("```")[0].strip()

        try:
            extracted_json = json.loads(response_str)
        except json.JSONDecodeError:
            start = response_str.find("{")
            end = response_str.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    extracted_json = json.loads(response_str[start : end + 1])
                except Exception:
                    extracted_json = {}
            else:
                extracted_json = {}


        def flatten_json_values(obj):
            values = []
            if isinstance(obj, Mapping):
                for v in obj.values():
                    values.extend(flatten_json_values(v))
            elif isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
                for item in obj:
                    values.extend(flatten_json_values(item))
            else:
                values.append(obj)
            return values


        answers_list = flatten_json_values(extracted_json)
        #print(answers_list)


        def set_field_value(annot, value):
            ft = annot.FT or (annot.Parent and annot.Parent.FT)

            if ft == "/Btn":
                is_checked = False
                if isinstance(value, bool):
                    is_checked = value
                elif isinstance(value, (int, float)):
                    is_checked = bool(value)
                elif isinstance(value, str):
                    is_checked = value.strip().lower() in ("true", "yes", "1", "x", "checked", "on")

                ap_n = annot.AP and annot.AP.N
                on_key = "Yes"
                if ap_n:
                    for k in ap_n.keys():
                        if k != "/Off":
                            on_key = k[1:] if k.startswith("/") else k
                            break

                state = on_key if is_checked else "Off"
                annot.V = PdfName(state)
                annot.AS = PdfName(state)

            elif ft in ("/Tx", "/Ch") or ft is None:
                if value is not None:
                    annot.V = f"{value}"
                    annot.AP = None


        pdf_file = Path(pdf_path)
        pdf = PdfReader(str(pdf_file))

        i = 0
        for page in pdf.pages:
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )

                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and (annot.T or (annot.Parent and annot.Parent.T)):
                        if i < len(answers_list):
                            set_field_value(annot, answers_list[i])
                            i += 1
                        else:
                            break

        PdfWriter().write(str(output_pdf_path), pdf)
        return extracted_json