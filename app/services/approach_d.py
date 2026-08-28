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

        """
        Incident Status Summary Briefing (ICS 209)
        General Incident & Header Information
        The Blackwood Canyon Wildfire, designated under incident number CA-TNF-003891, is being reported via Update Report #4 for the operational period spanning August 14, 2026, from 06:00 to 18:00 PDT. The incident originally started on August 11, 2026, at 14:15 PDT. The fire is being managed under a Unified Command consisting of Incident Commander R. Sterling from the US Forest Service and Incident Commander M. Torres from CAL FIRE. The incident complexity is classified at Level 1, actively covering 4,250 acres with 35% containment. The primary incident definition is a Wildfire burning through mixed conifer and heavy timber.
        The form was prepared by Situation Unit Leader J. Vance on August 14, 2026, at 17:30 PDT and officially approved by Incident Commander R. Sterling. It was routed to the Sierra Front Interagency Dispatch Center.
        Location & Geospatial Details
        The fire originated in Placer County, California, near Tahoe City. Geographic coordinates are recorded at Latitude 39°08'42" N, Longitude 120°09'35" W. The short location description notes the fire actively burning 4 miles southwest of Tahoe City, expanding west toward the Granite Chief Wilderness. Attached geospatial data includes an updated perimeter shapefile (blackwood_perim_20260814_1600.shp) collected at 16:00 PDT.
        Significant Events & Damage Assessment
        During this operational period, mandatory evacuations were expanded for Blackwood Canyon Road, affecting 150 residential properties. CAL FIRE completed 2.5 miles of direct dozer line along the southern flank. Severe structural impacts have been logged: 12 single residences are currently threatened (within 72 hours), 2 single residences have been damaged, and 5 single residences have been completely destroyed. Additionally, 3 nonresidential commercial properties are threatened, 1 is damaged, and 8 minor outbuildings/sheds have been destroyed.
        Public & Responder Status

        Public Status: During this period, 2 civilian injuries were reported (heat exhaustion during evacuation), bringing total civilian injuries to 5. Exactly 320 civilians have been evacuated to date (estimated 45 this reporting period). Currently, 85 civilians are in temporary shelters. There are 0 civilian fatalities.
        Responder Status: 1 responder was injured this period (ankle sprain), bringing total responder injuries to 3. No responder fatalities or missing personnel have been reported.
        Threat management status reflects Mass Notifications Completed, Evacuations in Progress, and Area Restrictions in Effect (Highway 89 lane restrictions).
        Weather Concerns & Projections
        Weather conditions remain critical with temperatures at 92°F, relative humidity dropping to 11%, and gusty winds from the Southwest at 18 mph (gusting to 30 mph). A Red Flag Warning is active until 22:00 PDT.
        Projections indicate:

        12 Hours: Fire expected to breach Ridge Line 4, pushing toward Ward Creek.
        24 Hours: Threatens 45 additional homes in Alpine Meadows.
        48 Hours: Potential to cross Highway 89 if winds persist.
        72 Hours: Expected growth up to 6,000 acres.
        Strategic Objectives & Critical Resource Needs
        The overarching strategic objective is to establish full perimeter containment along the western flank, protect critical power transmission infrastructure, and safely repopulate Blackwood Canyon by August 18, 2026.
        Critical resource needs prioritized by timeframe:

        12 Hours: 4 Type 1 Strike Teams (Engines), 2 Type 1 Helicopters.
        24 Hours: 3 Type 1 Hand Crews.
        48 Hours: 1 Mobile Communications Unit.
        Financials & Timeline Targets
        Estimated incident costs to date have reached $4,850,000, with a projected final cost of $9,200,000. Anticipated incident management completion date is set for August 20, 2026, with significant resource demobilization planned to start on August 18, 2026.
        Resource Commitment Ledger

        CAL FIRE: 12 Type 1 Fire Engines (48 personnel) and 4 Type 1 Dozers (8 personnel).
        US Forest Service: 6 Type 2 Hand Crews (120 personnel) and 2 Type 1 Helicopters (6 personnel).
        Placer County Sheriff: 8 Law Enforcement Units (16 personnel) handling traffic and evacuations.
        Additional Overhead: 25 unassigned management/overhead personnel.
        """

        """
        {
        "type": "object",
        "properties": {
            "1_incident_header": {
            "type": "object",
            "properties": {
                "incident_name": { "type": "string" },
                "incident_number": { "type": "string" },
                "report_version": { "type": "string" },
                "report_number": { "type": "string" },
                "incident_commanders": {
                "type": "array",
                "items": { "type": "string" }
                },
                "incident_start_datetime": { "type": "string" },
                "current_size_acres": { "type": "number" },
                "percent_contained": { "type": "integer" },
                "incident_definition": { "type": "string" },
                "complexity_level": { "type": "string" },
                "reporting_period": {
                "type": "object",
                "properties": {
                    "from": { "type": "string" },
                    "to": { "type": "string" }
                }
                }
            }
            },
            "2_approval_and_location": {
            "type": "object",
            "properties": {
                "prepared_by": {
                "type": "object",
                "properties": {
                    "name": { "type": "string" },
                    "role": { "type": "string" },
                    "datetime": { "type": "string" }
                }
                },
                "approved_by": {
                "type": "object",
                "properties": {
                    "name": { "type": "string" },
                    "role": { "type": "string" }
                }
                },
                "sent_to": { "type": "string" },
                "location": {
                "type": "object",
                "properties": {
                    "state": { "type": "string" },
                    "county": { "type": "string" },
                    "city": { "type": "string" },
                    "latitude": { "type": "string" },
                    "longitude": { "type": "string" },
                    "short_description": { "type": "string" }
                }
                },
                "geospatial_data_attached": { "type": "string" }
            }
            },
            "3_damage_assessment": {
            "type": "object",
            "properties": {
                "single_residences": {
                "type": "object",
                "properties": {
                    "threatened_72h": { "type": "integer" },
                    "damaged": { "type": "integer" },
                    "destroyed": { "type": "integer" }
                }
                },
                "commercial_properties": {
                "type": "object",
                "properties": {
                    "threatened_72h": { "type": "integer" },
                    "damaged": { "type": "integer" },
                    "destroyed": { "type": "integer" }
                }
                },
                "minor_structures": {
                "type": "object",
                "properties": {
                    "threatened_72h": { "type": "integer" },
                    "damaged": { "type": "integer" },
                    "destroyed": { "type": "integer" }
                }
                }
            }
            },
            "4_status_summaries": {
            "type": "object",
            "properties": {
                "civilians": {
                "type": "object",
                "properties": {
                    "injuries_this_period": { "type": "integer" },
                    "injuries_total": { "type": "integer" },
                    "evacuated_total": { "type": "integer" },
                    "in_shelters_current": { "type": "integer" },
                    "fatalities_total": { "type": "integer" }
                }
                },
                "responders": {
                "type": "object",
                "properties": {
                    "injuries_this_period": { "type": "integer" },
                    "injuries_total": { "type": "integer" },
                    "fatalities_total": { "type": "integer" }
                }
                },
                "active_threat_management_flags": {
                "type": "array",
                "items": { "type": "string" }
                }
            }
            },
            "5_projections_and_objectives": {
            "type": "object",
            "properties": {
                "weather_synopsis": { "type": "string" },
                "projected_activity": {
                "type": "object",
                "properties": {
                    "12_hours": { "type": "string" },
                    "24_hours": { "type": "string" },
                    "48_hours": { "type": "string" },
                    "72_hours": { "type": "string" }
                }
                },
                "strategic_objectives": { "type": "string" },
                "critical_resource_needs": {
                "type": "object",
                "properties": {
                    "12_hours": { "type": "array", "items": { "type": "string" } },
                    "24_hours": { "type": "array", "items": { "type": "string" } },
                    "48_hours": { "type": "array", "items": { "type": "string" } }
                }
                }
            }
            },
            "6_financials_and_timeline": {
            "type": "object",
            "properties": {
                "estimated_costs_to_date_usd": { "type": "integer" },
                "projected_final_cost_usd": { "type": "integer" },
                "anticipated_completion_date": { "type": "string" },
                "demobilization_start_date": { "type": "string" }
            }
            },
            "7_resource_commitment": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                "agency": { "type": "string" },
                "resource_type": { "type": "string" },
                "count": { "type": "integer" },
                "personnel_count": { "type": "integer" }
                }
            }
            }
        }
        }
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