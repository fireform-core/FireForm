from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class IncidentReport(BaseModel):
    """
    Canonical schema for a FireForm incident report.

    All fields are Optional. Fields that could not be reliably extracted by the
    LLM are recorded in `requires_review` so responders can spot what needs
    manual completion before the PDF is submitted.

    This schema serves three roles:
      1. LLM target  - the JSON structure the extraction prompt asks for.
      2. Validator   - Pydantic validates the LLM response against this model.
      3. Mapper source - TemplateMapper resolves json_path values from this model
                         to populate PDF form fields.

    Note: `requires_review` is populated by the extraction pipeline, never by
    the LLM itself. Exclude it when building the schema hint sent to the model.
    """

    # Identity
    incident_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for this incident assigned by the agency.",
        examples=["CAL-2024-001", "INC-20240101-005"],
    )
    agency_id: Optional[str] = Field(
        default=None,
        description="Name or identifier of the responding agency.",
        examples=["CAL FIRE", "SFFD", "LAFD"],
    )
    unit_ids: Optional[list[str]] = Field(
        default=None,
        description=(
            "List of unit or apparatus identifiers responding to the incident. "
            "If multiple units are named, list all of them."
        ),
        examples=[["Engine 12", "Truck 4"], ["Unit 7", "Medic 3"]],
    )

    # Incident classification
    incident_type: Optional[str] = Field(
        default=None,
        description=(
            "Type or category of the incident. Use a short lowercase label. "
            "Common values: wildfire, structure_fire, vehicle_accident, EMS, hazmat, rescue."
        ),
        examples=["wildfire", "structure_fire", "EMS", "vehicle_accident", "hazmat"],
    )
    incident_severity: Optional[str] = Field(
        default=None,
        description="Severity or alarm level of the incident.",
        examples=["low", "moderate", "high", "major"],
    )

    # Location
    location_address: Optional[str] = Field(
        default=None,
        description="Street address or nearest landmark address of the incident.",
        examples=["1234 Oak Street", "Highway 1 near Mile Marker 42"],
    )
    location_city: Optional[str] = Field(
        default=None,
        description="City where the incident occurred.",
        examples=["San Francisco", "Half Moon Bay"],
    )
    location_county: Optional[str] = Field(
        default=None,
        description="County where the incident occurred.",
        examples=["San Mateo County", "Los Angeles County"],
    )
    location_state: Optional[str] = Field(
        default=None,
        description="State abbreviation or full name where the incident occurred.",
        examples=["CA", "California"],
    )
    location_coordinates: Optional[str] = Field(
        default=None,
        description="GPS coordinates in decimal degrees format: 'latitude, longitude'.",
        examples=["37.7749, -122.4194"],
    )

    # Timestamps (stored as strings - the LLM extracts them as spoken/written)
    alarm_time: Optional[str] = Field(
        default=None,
        description=(
            "Time the alarm was received or the incident was reported. "
            "Use HH:MM (24-hour) if possible, or reproduce the exact phrasing."
        ),
        examples=["14:35", "2:35 PM", "1435 hours"],
    )
    dispatch_time: Optional[str] = Field(
        default=None,
        description="Time units were dispatched to the incident.",
        examples=["14:37", "1437 hours"],
    )
    arrival_time: Optional[str] = Field(
        default=None,
        description="Time the first unit arrived on scene.",
        examples=["14:45", "1445 hours"],
    )
    controlled_time: Optional[str] = Field(
        default=None,
        description="Time the incident was declared under control.",
        examples=["17:20", "1720 hours"],
    )
    clear_time: Optional[str] = Field(
        default=None,
        description="Time all units cleared the scene.",
        examples=["18:05", "1805 hours"],
    )
    incident_date: Optional[str] = Field(
        default=None,
        description="Date the incident occurred.",
        examples=["2024-01-01", "January 1, 2024", "01/01/2024"],
    )

    # Personnel
    supervisor: Optional[str] = Field(
        default=None,
        description=(
            "Name or identifier of the incident commander or supervising officer "
            "in charge at the scene."
        ),
        examples=["Battalion Chief Johnson", "Captain Maria Torres"],
    )
    personnel: Optional[list[str]] = Field(
        default=None,
        description=(
            "Names or identifiers of all personnel assigned to the incident. "
            "Include rank or role if mentioned."
        ),
        examples=[["FF Smith", "FF Jones", "Paramedic Lee"]],
    )
    personnel_count: Optional[int] = Field(
        default=None,
        description="Total number of personnel responding to the incident.",
        examples=[6, 12],
    )

    # Casualties and medical (EMS / law enforcement forms)
    casualties: Optional[int] = Field(
        default=None,
        description="Total number of injured persons (civilians and/or responders).",
        examples=[2, 0],
    )
    fatalities: Optional[int] = Field(
        default=None,
        description="Total number of fatalities resulting from the incident.",
        examples=[0, 1],
    )
    patients_transported: Optional[int] = Field(
        default=None,
        description="Number of patients transported to a medical facility.",
        examples=[1, 3],
    )
    hospital_destination: Optional[str] = Field(
        default=None,
        description="Name or identifier of the hospital patients were transported to.",
        examples=["SF General Hospital", "UCLA Medical Center"],
    )
    patient_condition: Optional[str] = Field(
        default=None,
        description="Reported condition of the patient(s) at time of transport or care.",
        examples=["stable", "critical", "deceased"],
    )

    # Narrative
    narrative: Optional[str] = Field(
        default=None,
        description=(
            "Free-text description of the incident: what happened, actions taken "
            "by responders, and the outcome. Reproduce faithfully from the transcript."
        ),
        examples=[
            "Crews arrived to find a one-story structure with heavy smoke showing "
            "from the roof. A primary search revealed no occupants. Fire was "
            "knocked down within 20 minutes. Cause determined to be electrical."
        ],
    )

    # Wildfire-specific (Cal Fire FIRESCOPE)
    area_burned_acres: Optional[float] = Field(
        default=None,
        description="Estimated area burned in acres. Wildfire incidents only.",
        examples=[12.5, 0.25],
    )
    structures_threatened: Optional[int] = Field(
        default=None,
        description="Number of structures threatened by the incident.",
        examples=[15, 0],
    )
    structures_destroyed: Optional[int] = Field(
        default=None,
        description="Number of structures destroyed.",
        examples=[3, 0],
    )
    containment_percent: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Percentage of wildfire perimeter that is contained (0-100).",
        examples=[25, 100],
    )
    fuel_type: Optional[str] = Field(
        default=None,
        description="Predominant fuel type involved in the wildfire.",
        examples=["grass", "chaparral", "timber", "brush"],
    )

    # Law enforcement (incident/crime report forms)
    case_number: Optional[str] = Field(
        default=None,
        description="Law enforcement case or report number.",
        examples=["SFPD-2024-00123"],
    )
    officer_id: Optional[str] = Field(
        default=None,
        description="Badge number or identifier of the reporting officer.",
        examples=["Badge #4821"],
    )
    suspect_description: Optional[str] = Field(
        default=None,
        description="Physical description or identifying information of any suspect.",
        examples=["Male, approximately 30 years old, 6ft, wearing a red jacket"],
    )

    # Pipeline metadata - populated by the extraction pipeline, not the LLM
    requires_review: list[str] = Field(
        default_factory=list,
        description=(
            "Field names that could not be reliably extracted and require human "
            "review before the PDF is submitted. Populated by the retry loop, "
            "never by the LLM."
        ),
    )

    @model_validator(mode="after")
    def collect_missing_fields(self) -> "IncidentReport":
        """
        Populate requires_review with core field names still set to None.
        """
        core_fields = {
            "incident_type",
            "location_address",
            "location_city",
            "alarm_time",
            "incident_date",
            "supervisor",
            "narrative",
        }
        missing = [field for field in core_fields if getattr(self, field) is None]
        if not self.requires_review:
            self.requires_review = missing
        return self

    @classmethod
    def llm_schema_hint(cls) -> dict:
        """
        Return a JSON-serializable schema hint for LLM extraction.

        Excludes `requires_review` because it is pipeline-owned metadata.
        """
        schema = cls.model_json_schema()
        excluded = {"requires_review"}
        properties = {
            key: value
            for key, value in schema.get("properties", {}).items()
            if key not in excluded
        }
        return {
            "type": "object",
            "properties": properties,
            "required": [],
        }
