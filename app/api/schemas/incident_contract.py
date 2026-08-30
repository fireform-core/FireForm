# This file is generated from contracts/schemas/incident-contract.yaml.
# DO NOT EDIT BY HAND. Run `make generate-contract-models` to regenerate.

from __future__ import annotations

from datetime import date as date_type, time as time_type
from enum import Enum
from typing import Annotated, Any, Optional
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, RootModel
from app.api.schemas.enums import (
    CauseCertainty,
    IncidentCategory,
    InjurySeverity,
    RateOfSpread,
    ReportStatus,
)


class SchemaName(Enum):
    """
    Schema name identifier
    """

    fireform_incident_contract = "fireform_incident_contract"


class Money(BaseModel):
    """
    Monetary amount with ISO 4217 currency code
    """

    amount: Optional[float] = None
    currency: Annotated[Optional[str], Field(None, examples=["USD"])]
    """
    ISO 4217 code
    """


class Scheme(Enum):
    """
    Coding scheme identifier
    """

    neris = "neris"
    nfirs = "nfirs"
    uk_irs = "uk_irs"
    airs = "airs"
    ontario_sir = "ontario_sir"
    nemsis = "nemsis"
    nibrs = "nibrs"
    un_ssirs = "un_ssirs"
    local = "local"
    other = "other"


class CodeRef(BaseModel):
    """
    A code from a named external coding scheme
    """

    scheme: Optional[Scheme] = None
    """
    Coding scheme identifier
    """
    code: Optional[str] = None
    label: Optional[str] = None


class Quantity(BaseModel):
    """
    Value with explicit reported unit, used where the unit itself is data (hazmat)
    """

    value: Optional[float] = None
    unit: Optional[str] = None
    """
    Unit as reported (e.g. l, kg, gal, lb, m3)
    """


class PresenceStatus(Enum):
    present = "present"
    absent = "absent"
    undetermined = "undetermined"


class OperationStatus(Enum):
    """
    Whether a protection system operated when exposed to the incident
    """

    operated = "operated"
    failed_to_operate = "failed_to_operate"
    fire_too_small_to_activate = "fire_too_small_to_activate"
    not_reached_by_fire = "not_reached_by_fire"
    undetermined = "undetermined"


class Coordinates(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_meters: Optional[float] = None


class InputType(Enum):
    voice = "voice"
    text = "text"


class Completeness(BaseModel):
    """
    Extraction-quality summary, recalculated server-side after every
    PATCH /extract. Per-template readiness is not stored here; it is
    computed live by GET /extract/{extract_id}/readiness against the
    registered templates.

    """

    overall_percent: Annotated[Optional[int], Field(None, ge=0, le=100)]
    missing_fields: Optional[list[str]] = None
    """
    JSON paths of fields that have no value
    """
    low_confidence_fields: Optional[list[str]] = None
    """
    JSON paths of fields where LLM confidence is low
    """
    inferred_fields: Optional[list[str]] = None
    """
    JSON paths of fields that were inferred (not explicitly stated)
    """


class ExternalId(BaseModel):
    scheme: Annotated[Optional[str], Field(None, examples=["irwin"])]
    value: Optional[str] = None


class FormType(RootModel[Optional[str]]):
    root: Annotated[Optional[str], Field(None, examples=["neris"])] = None
    """
    Stable string identifier for a form type. An open string, not a closed
    enum, because users register their own templates (any jurisdiction, any
    agency) and each carries its own form_type label. Generation and
    validation are keyed by template_id; form_type is a human-friendly label
    and grouping key.

    Well-known built-in values: neris, nemsis_epcr, nibrs, nfirs_basic,
    nfirs_fire, nfirs_structure, nfirs_wildland, nfirs_ems, nfirs_hazmat,
    nfirs_apparatus, nfirs_personnel, nfirs_arson, nfirs_casualty_civilian,
    nfirs_casualty_responder, cal_fire_ics209, osha_301, un_ssirs,
    state_georgia, state_california, state_new_york.

    """


class ReportingUnit(BaseModel):
    station_name: Optional[str] = None
    station_id: Optional[str] = None
    agency_name: Optional[str] = None
    agency_id: Optional[UUID] = None
    agency_type: Optional[str] = None


class Personnel(BaseModel):
    name: Optional[str] = None
    badge_number: Optional[str] = None
    rank: Optional[str] = None
    role: Optional[str] = None
    assignment: Optional[str] = None
    contact_number: Optional[str] = None
    signature_captured: Optional[bool] = None


class Reviewer(BaseModel):
    name: Optional[str] = None
    badge_number: Optional[str] = None
    rank: Optional[str] = None
    role: Optional[str] = None
    reviewed_at: Optional[AwareDatetime] = None
    approved: Optional[bool] = None


class Reason(Enum):
    malicious = "malicious"
    good_intent = "good_intent"
    automatic_system_fault = "automatic_system_fault"
    automatic_system_accidental = "automatic_system_accidental"
    human_error = "human_error"
    undetermined = "undetermined"
    other = "other"


class FalseAlarm(BaseModel):
    """
    Populated when the final type is a false alarm
    """

    reason: Optional[Reason] = None
    reason_description: Optional[str] = None


class DelayIgnitionToDiscovery(Enum):
    immediate = "immediate"
    under_5_min = "under_5_min"
    field_5_to_30_min = "5_to_30_min"
    over_30_min = "over_30_min"
    undetermined = "undetermined"


class DelayDiscoveryToCall(Enum):
    immediate = "immediate"
    under_5_min = "under_5_min"
    field_5_to_30_min = "5_to_30_min"
    over_30_min = "over_30_min"
    undetermined = "undetermined"


class CallOrigin(Enum):
    person_landline = "person_landline"
    person_mobile = "person_mobile"
    person_in_person = "person_in_person"
    automatic_alarm_originator = "automatic_alarm_originator"
    automatic_alarm_monitoring_center = "automatic_alarm_monitoring_center"
    other_agency = "other_agency"
    police = "police"
    ambulance = "ambulance"
    coastguard = "coastguard"
    other_fire_service = "other_fire_service"
    other = "other"
    undetermined = "undetermined"


class DispatcherComment(BaseModel):
    comment: Optional[str] = None
    timestamp: Optional[AwareDatetime] = None


class Dispatch(BaseModel):
    """
    Call handling data, usually pre-populated from CAD/PSAP when available
    """

    psap_id: Optional[str] = None
    """
    Dispatch center / PSAP identifier
    """
    dispatch_center: Optional[str] = None
    """
    Dispatch center name
    """
    cad_event_id: Optional[str] = None
    call_received_datetime: Optional[AwareDatetime] = None
    """
    Call arrived at PSAP or department dispatch center
    """
    call_answered_datetime: Optional[AwareDatetime] = None
    call_created_datetime: Optional[AwareDatetime] = None
    """
    CAD event created
    """
    first_unit_dispatched_datetime: Optional[AwareDatetime] = None
    call_origin: Optional[CallOrigin] = None
    automatic_alarm: Optional[bool] = None
    """
    Call originated from an automatic alarm system
    """
    incident_type_at_dispatch: Optional[str] = None
    """
    Incident type as received by the control room; may differ from final type
    """
    determinate_code: Optional[str] = None
    """
    Output code from the dispatch protocol (e.g. EMD/ProQA)
    """
    priority_at_call: Annotated[Optional[int], Field(None, ge=1, le=5)]
    dispatcher_comments: Optional[list[DispatcherComment]] = None


class LocationType(Enum):
    street_address = "street_address"
    intersection = "intersection"
    milepost_or_highway = "milepost_or_highway"
    coordinates_only = "coordinates_only"
    unaddressable_area = "unaddressable_area"
    water_body = "water_body"
    other = "other"


class Scheme1(Enum):
    usng = "usng"
    mgrs = "mgrs"
    utm = "utm"
    osgb = "osgb"
    other = "other"


class GridReference(BaseModel):
    """
    National grid reference where used instead of lat/long
    """

    scheme: Optional[Scheme1] = None
    value: Optional[str] = None


class Jurisdiction(BaseModel):
    federal: Optional[bool] = None
    state: Optional[bool] = None
    private: Optional[bool] = None
    tribal: Optional[bool] = None


class OwnershipAtOrigin(Enum):
    """
    Ownership of the property at the point of origin
    """

    private = "private"
    city_or_local = "city_or_local"
    county = "county"
    state_or_province = "state_or_province"
    federal = "federal"
    tribal = "tribal"
    military = "military"
    foreign = "foreign"
    other = "other"
    undetermined = "undetermined"


class PopulationDensity(Enum):
    urban = "urban"
    suburban = "suburban"
    rural = "rural"
    wilderness = "wilderness"


class OverBorder(BaseModel):
    """
    Incident on another service's ground (UK IRS 1.5-1.7)
    """

    is_over_border: Optional[bool] = None
    other_service_name: Optional[str] = None
    other_service_incident_number: Optional[str] = None


class Location(BaseModel):
    location_type: Optional[LocationType] = None
    address: Optional[str] = None
    """
    Full street address as one line
    """
    cross_streets: Optional[list[str]] = None
    """
    Nearest cross street(s)
    """
    nearest_landmark: Optional[str] = None
    city: Optional[str] = None
    """
    City, town or nearest settlement
    """
    district_or_zone: Optional[str] = None
    """
    Administrative district, borough or fire zone
    """
    county: Optional[str] = None
    state: Optional[str] = None
    """
    State, province or region
    """
    country: Annotated[Optional[str], Field(None, examples=["US"])]
    """
    ISO 3166-1 alpha-2 code preferred
    """
    postal_code: Optional[str] = None
    census_area: Optional[str] = None
    """
    Census tract or national statistical area code
    """
    coordinates: Optional[Coordinates] = None
    ignition_point_coordinates: Optional[Coordinates] = None
    grid_reference: Optional[GridReference] = None
    """
    National grid reference where used instead of lat/long
    """
    elevation_m: Optional[float] = None
    legal_description: Optional[str] = None
    """
    Township / section / range or equivalent cadastral reference
    """
    jurisdiction: Optional[Jurisdiction] = None
    ownership_at_origin: Optional[OwnershipAtOrigin] = None
    """
    Ownership of the property at the point of origin
    """
    population_density: Optional[PopulationDensity] = None
    property_type: Optional[str] = None
    property_use: Optional[str] = None
    """
    Use of the property at the time (residential, commercial, school...)
    """
    property_use_codes: Optional[list[CodeRef]] = None
    """
    Property use in external coding schemes (NFIRS 3-digit, NERIS location use)
    """
    mixed_use: Optional[str] = None
    """
    Mixed-use classification when the property has multiple uses
    """
    over_border: Optional[OverBorder] = None
    """
    Incident on another service's ground (UK IRS 1.5-1.7)
    """


class Category(Enum):
    fire_suppression = "fire_suppression"
    search = "search"
    rescue = "rescue"
    ems_care = "ems_care"
    extrication = "extrication"
    hazmat_mitigation = "hazmat_mitigation"
    ventilation = "ventilation"
    forcible_entry = "forcible_entry"
    salvage_overhaul = "salvage_overhaul"
    water_supply = "water_supply"
    exposure_protection = "exposure_protection"
    evacuation = "evacuation"
    command_control = "command_control"
    investigation = "investigation"
    public_assist = "public_assist"
    standby = "standby"
    information_referral = "information_referral"
    systems_restoration = "systems_restoration"
    other = "other"


class Action(BaseModel):
    category: Optional[Category] = None
    description: Optional[str] = None
    codes: Optional[list[CodeRef]] = None


class ActionsTaken(BaseModel):
    """
    What responders did on scene. Every reporting standard requires this.
    """

    actions: Optional[list[Action]] = None
    no_action_reason: Optional[str] = None
    """
    Why no action was taken (canceled enroute, no hazard found...)
    """


class AidDirection(Enum):
    given = "given"
    received = "received"
    both = "both"
    none = "none"


class AidType(Enum):
    automatic = "automatic"
    mutual = "mutual"
    other = "other"
    none = "none"


class IncidentCommander(BaseModel):
    name: Optional[str] = None
    agency: Optional[str] = None
    position: Optional[str] = None


class RespondingAgency(BaseModel):
    agency_name: Optional[str] = None
    agency_type: Optional[str] = None
    """
    fire, ems, police, forestry, military, utility, ngo, other
    """
    role: Optional[str] = None
    personnel_count: Optional[int] = None
    incident_number_at_agency: Optional[str] = None
    """
    That agency's own incident number for cross-referencing
    """


class ApparatusType(Enum):
    engine_pumper = "engine_pumper"
    ladder_aerial = "ladder_aerial"
    quint = "quint"
    tanker_tender = "tanker_tender"
    brush_wildland = "brush_wildland"
    arff = "arff"
    dozer_plow = "dozer_plow"
    heavy_equipment = "heavy_equipment"
    aircraft_fixed_wing = "aircraft_fixed_wing"
    helicopter = "helicopter"
    boat = "boat"
    rescue_unit = "rescue_unit"
    usar_unit = "usar_unit"
    hazmat_unit = "hazmat_unit"
    ambulance_bls = "ambulance_bls"
    ambulance_als = "ambulance_als"
    command_vehicle = "command_vehicle"
    support_unit = "support_unit"
    hand_crew = "hand_crew"
    privately_owned = "privately_owned"
    other = "other"


class Use(Enum):
    suppression = "suppression"
    ems = "ems"
    rescue = "rescue"
    hazmat = "hazmat"
    command = "command"
    support = "support"
    other = "other"


class PersonnelItem(BaseModel):
    personnel_id: Optional[str] = None
    name: Optional[str] = None
    rank: Optional[str] = None
    role: Optional[str] = None


class ResponseMode(Enum):
    emergency_lights_siren = "emergency_lights_siren"
    non_emergency = "non_emergency"
    undetermined = "undetermined"


class TransportMode(Enum):
    emergency_lights_siren = "emergency_lights_siren"
    non_emergency = "non_emergency"
    undetermined = "undetermined"


class UnitResponse(BaseModel):
    """
    One responding unit (apparatus or resource) and its timeline
    """

    unit_id: Optional[str] = None
    """
    Callsign or unit identifier
    """
    unit_name: Optional[str] = None
    agency_name: Optional[str] = None
    apparatus_type: Optional[ApparatusType] = None
    use: Optional[Use] = None
    personnel_count: Optional[int] = None
    personnel: Optional[list[PersonnelItem]] = None
    response_mode: Optional[ResponseMode] = None
    canceled_enroute: Optional[bool] = None
    dispatched_datetime: Optional[AwareDatetime] = None
    enroute_datetime: Optional[AwareDatetime] = None
    arrived_datetime: Optional[AwareDatetime] = None
    staged_datetime: Optional[AwareDatetime] = None
    at_patient_datetime: Optional[AwareDatetime] = None
    enroute_hospital_datetime: Optional[AwareDatetime] = None
    arrived_hospital_datetime: Optional[AwareDatetime] = None
    transfer_of_care_datetime: Optional[AwareDatetime] = None
    cleared_datetime: Optional[AwareDatetime] = None
    in_service_datetime: Optional[AwareDatetime] = None
    """
    Back available for calls
    """
    turnout_seconds: Optional[int] = None
    """
    Computed, dispatched to enroute
    """
    travel_seconds: Optional[int] = None
    """
    Computed, enroute to arrived
    """
    transport_mode: Optional[TransportMode] = None
    hospital_destination: Optional[str] = None
    actions_taken: Optional[list[str]] = None
    """
    Actions by this unit, same categories as incident actions
    """


class PersonnelBreakdown(BaseModel):
    firefighters: Optional[int] = None
    officers: Optional[int] = None
    engineers_operators: Optional[int] = None
    ems_personnel: Optional[int] = None
    incident_command: Optional[int] = None
    support_staff: Optional[int] = None


class ApparatusCounts(BaseModel):
    """
    Unit counts by primary use (NFIRS Basic G1)
    """

    suppression: Optional[int] = None
    ems: Optional[int] = None
    other: Optional[int] = None


class ResourcesSummary(BaseModel):
    """
    Aggregate counts; per-unit detail lives in units[]
    """

    total_personnel: Optional[int] = None
    personnel_breakdown: Optional[PersonnelBreakdown] = None
    apparatus_counts: Optional[ApparatusCounts] = None
    """
    Unit counts by primary use (NFIRS Basic G1)
    """
    crew_types: Optional[list[str]] = None
    """
    Wildland crew types deployed (hand crew type 1/2, engine crew...)
    """
    counts_include_aid_received: Optional[bool] = None


class CauseCategory(Enum):
    intentional = "intentional"
    unintentional = "unintentional"
    equipment_failure = "equipment_failure"
    act_of_nature = "act_of_nature"
    cause_under_investigation = "cause_under_investigation"
    undetermined = "undetermined"
    other = "other"


class HumanFactor(Enum):
    asleep = "asleep"
    impaired_by_alcohol_or_drugs = "impaired_by_alcohol_or_drugs"
    unattended_person = "unattended_person"
    mentally_disabled = "mentally_disabled"
    physically_disabled = "physically_disabled"
    multiple_persons_involved = "multiple_persons_involved"
    age_was_factor = "age_was_factor"
    other = "other"


class Portability(Enum):
    portable = "portable"
    stationary = "stationary"


class EquipmentInvolved(BaseModel):
    """
    Equipment involved in ignition, if any
    """

    involved: Optional[bool] = None
    equipment_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    year: Optional[int] = None
    power_source: Optional[str] = None
    portability: Optional[Portability] = None


class WaterSupplyType(Enum):
    pressurized_hydrant = "pressurized_hydrant"
    rural_water_supply = "rural_water_supply"
    tanker_shuttle = "tanker_shuttle"
    drafting_static_source = "drafting_static_source"
    onboard_water_only = "onboard_water_only"
    none_needed = "none_needed"
    other = "other"
    undetermined = "undetermined"


class ExtinguishingAgent(Enum):
    water = "water"
    foam = "foam"
    co2 = "co2"
    dry_chemical = "dry_chemical"
    wet_chemical = "wet_chemical"
    halon_clean_agent = "halon_clean_agent"
    sand_earth = "sand_earth"
    blanket_smothering = "blanket_smothering"
    other = "other"


class EquipmentUsedItem(BaseModel):
    equipment_type: Optional[str] = None
    count: Optional[int] = None


class FirefightingDelay(BaseModel):
    occurred: Optional[bool] = None
    reason: Optional[str] = None


class SuppressionOperations(BaseModel):
    water_supply_type: Optional[WaterSupplyType] = None
    water_used_l: Optional[float] = None
    extinguishing_agents: Optional[list[ExtinguishingAgent]] = None
    suppression_appliances: Optional[list[str]] = None
    """
    Appliances used for suppression (jets, hose reels, monitors, extinguishers)
    """
    equipment_used: Optional[list[EquipmentUsedItem]] = None
    """
    Equipment used at the incident with counts (UK IRS 6.16-6.17)
    """
    ba_wearers_count: Optional[int] = None
    """
    Breathing apparatus wearers
    """
    firefighting_delay: Optional[FirefightingDelay] = None
    public_action_before_arrival: Optional[str] = None
    """
    Main action taken by the public before responders arrived
    """


class Stage(Enum):
    before_fire = "before_fire"
    during_fire = "during_fire"
    after_fire = "after_fire"
    no_fire = "no_fire"


class Explosion(BaseModel):
    """
    Explosion or overpressure event, with or without fire (UK IRS 8.10-8.13)
    """

    occurred: Optional[bool] = None
    cause: Optional[str] = None
    stage: Optional[Stage] = None
    containers_involved: Optional[list[str]] = None


class AlarmType(Enum):
    smoke = "smoke"
    heat = "heat"
    combination = "combination"
    sprinkler_waterflow = "sprinkler_waterflow"
    multiple_types = "multiple_types"
    other = "other"
    undetermined = "undetermined"


class PowerSupply(Enum):
    battery_only = "battery_only"
    hardwire_only = "hardwire_only"
    hardwire_with_battery = "hardwire_with_battery"
    plug_in = "plug_in"
    plug_in_with_battery = "plug_in_with_battery"
    mechanical = "mechanical"
    multiple = "multiple"
    other = "other"
    undetermined = "undetermined"


class Effectiveness(Enum):
    alerted_occupants_responded = "alerted_occupants_responded"
    alerted_occupants_no_response = "alerted_occupants_no_response"
    no_occupants = "no_occupants"
    failed_to_alert = "failed_to_alert"
    undetermined = "undetermined"


class FailureReason(Enum):
    power_failure_or_disconnect = "power_failure_or_disconnect"
    improper_installation = "improper_installation"
    defective = "defective"
    lack_of_maintenance = "lack_of_maintenance"
    battery_missing = "battery_missing"
    battery_dead = "battery_dead"
    other = "other"
    undetermined = "undetermined"


class SmokeAlarm(BaseModel):
    presence: Optional[PresenceStatus] = None
    alarm_type: Optional[AlarmType] = None
    power_supply: Optional[PowerSupply] = None
    working: Optional[bool] = None
    operation: Optional[OperationStatus] = None
    effectiveness: Optional[Effectiveness] = None
    failure_reason: Optional[FailureReason] = None
    occupant_response: Optional[str] = None


class FireAlarm(BaseModel):
    """
    Building fire alarm system
    """

    presence: Optional[PresenceStatus] = None
    alarm_type: Optional[str] = None
    monitored: Optional[bool] = None
    operation: Optional[OperationStatus] = None
    failure_reason: Optional[str] = None


class OtherAlarm(BaseModel):
    """
    CO, gas, security or other alarm
    """

    presence: Optional[PresenceStatus] = None
    alarm_type: Optional[str] = None


class SystemType(Enum):
    wet_pipe_sprinkler = "wet_pipe_sprinkler"
    dry_pipe_sprinkler = "dry_pipe_sprinkler"
    other_sprinkler = "other_sprinkler"
    dry_chemical = "dry_chemical"
    foam = "foam"
    halon_clean_agent = "halon_clean_agent"
    co2 = "co2"
    water_mist = "water_mist"
    other_special_hazard = "other_special_hazard"
    other = "other"
    undetermined = "undetermined"


class Coverage(Enum):
    full = "full"
    partial = "partial"
    undetermined = "undetermined"


class FailureReason1(Enum):
    system_shut_off = "system_shut_off"
    not_enough_agent = "not_enough_agent"
    agent_did_not_reach_fire = "agent_did_not_reach_fire"
    wrong_system_type = "wrong_system_type"
    fire_outside_protected_area = "fire_outside_protected_area"
    components_damaged = "components_damaged"
    lack_of_maintenance = "lack_of_maintenance"
    manual_intervention = "manual_intervention"
    other = "other"
    undetermined = "undetermined"


class SuppressionSystem(BaseModel):
    """
    Automatic extinguishing system
    """

    presence: Optional[PresenceStatus] = None
    system_type: Optional[SystemType] = None
    coverage: Optional[Coverage] = None
    operation: Optional[OperationStatus] = None
    sprinkler_heads_activated: Optional[int] = None
    effective: Optional[bool] = None
    failure_reason: Optional[FailureReason1] = None


class CookingSuppression(BaseModel):
    presence: Optional[PresenceStatus] = None
    system_type: Optional[str] = None


class FixedFirefightingFacility(BaseModel):
    facility_type: Optional[str] = None
    used: Optional[bool] = None
    worked: Optional[bool] = None
    failure_reason: Optional[str] = None


class RiskReduction(BaseModel):
    """
    Alarms, detectors and suppression systems and how they performed
    """

    smoke_alarm: Optional[SmokeAlarm] = None
    fire_alarm: Optional[FireAlarm] = None
    """
    Building fire alarm system
    """
    other_alarm: Optional[OtherAlarm] = None
    """
    CO, gas, security or other alarm
    """
    suppression_system: Optional[SuppressionSystem] = None
    """
    Automatic extinguishing system
    """
    cooking_suppression: Optional[CookingSuppression] = None
    fixed_firefighting_facilities: Optional[list[FixedFirefightingFacility]] = None
    """
    Built-in firefighting facilities (risers, hose reels, smoke control, fire lift)
    """


class BuildingStatus(Enum):
    occupied_in_use = "occupied_in_use"
    vacant_secured = "vacant_secured"
    vacant_unsecured = "vacant_unsecured"
    under_construction = "under_construction"
    under_renovation = "under_renovation"
    under_demolition = "under_demolition"
    derelict = "derelict"
    undetermined = "undetermined"


class FireSpreadExtent(Enum):
    confined_to_object = "confined_to_object"
    confined_to_room = "confined_to_room"
    confined_to_floor = "confined_to_floor"
    confined_to_building = "confined_to_building"
    beyond_building = "beyond_building"
    no_flame_damage = "no_flame_damage"
    undetermined = "undetermined"


class ArrivalConditions(Enum):
    no_visible_smoke_or_fire = "no_visible_smoke_or_fire"
    smoke_showing = "smoke_showing"
    fire_showing = "fire_showing"
    fully_involved = "fully_involved"
    collapsed = "collapsed"
    undetermined = "undetermined"


class StoriesDamaged(BaseModel):
    """
    Count of stories by flame damage band (NFIRS-3 J3)
    """

    minor: Optional[int] = None
    """
    1-24% flame damage
    """
    significant: Optional[int] = None
    """
    25-49% flame damage
    """
    heavy: Optional[int] = None
    """
    50-74% flame damage
    """
    extreme: Optional[int] = None
    """
    75-100% flame damage
    """


class Structure(BaseModel):
    is_structure_involved: Optional[bool] = None
    structures_threatened: Optional[int] = None
    structures_damaged: Optional[int] = None
    structures_destroyed: Optional[int] = None
    structures_protected: Optional[int] = None
    buildings_involved: Optional[int] = None
    """
    Number of buildings involved at the origin property
    """
    building_status: Optional[BuildingStatus] = None
    construction_type: Optional[str] = None
    construction_codes: Optional[list[CodeRef]] = None
    special_construction_method: Optional[str] = None
    """
    Notable construction method involved (timber frame, sandwich panel, cladding system)
    """
    stories_above_grade: Optional[int] = None
    stories_below_grade: Optional[int] = None
    total_floor_area_m2: Optional[float] = None
    main_floor_area_m2: Optional[float] = None
    residential_units: Optional[int] = None
    """
    Residential living units in the building of origin
    """
    occupancy_at_time: Optional[int] = None
    """
    Estimated number of people in the building at the time
    """
    fire_safety_regulations_apply: Optional[bool] = None
    means_of_escape_condition: Optional[str] = None
    compartmentation_effective: Optional[bool] = None
    story_of_origin: Optional[int] = None
    """
    Negative below grade, 1 is ground floor
    """
    room_of_origin: Optional[str] = None
    room_of_origin_area_m2: Optional[float] = None
    floor_of_origin_area_m2: Optional[float] = None
    fire_spread_extent: Optional[FireSpreadExtent] = None
    item_contributing_most_to_spread: Optional[str] = None
    material_contributing_most_to_spread: Optional[str] = None
    arrival_conditions: Optional[ArrivalConditions] = None
    progressed_beyond_arrival: Optional[bool] = None
    """
    Fire extended beyond the conditions found on arrival
    """
    smoke_damage_only: Optional[bool] = None
    """
    Heat/smoke damage with no flame damage (UK IRS 8.19)
    """
    stories_damaged: Optional[StoriesDamaged] = None
    """
    Count of stories by flame damage band (NFIRS-3 J3)
    """
    damage_area_on_arrival_m2: Optional[float] = None
    damage_area_at_stop_m2: Optional[float] = None
    """
    Horizontal area damaged by flame/heat when fire was stopped
    """


class AreaType(Enum):
    urban = "urban"
    suburban = "suburban"
    rural = "rural"
    wildland_urban_interface = "wildland_urban_interface"
    remote_wilderness = "remote_wilderness"


class LandOwnershipBreakdown(BaseModel):
    federal_ha: Optional[float] = None
    state_ha: Optional[float] = None
    private_ha: Optional[float] = None
    tribal_ha: Optional[float] = None
    other_ha: Optional[float] = None


class FireDangerRating(Enum):
    """
    Fire danger rating in effect at the time
    """

    low = "low"
    moderate = "moderate"
    high = "high"
    very_high = "very_high"
    severe = "severe"
    extreme = "extreme"
    catastrophic = "catastrophic"


class ComplexityLevel(Enum):
    """
    Incident complexity (type 5 lowest, type 1 highest)
    """

    type_5 = "type_5"
    type_4 = "type_4"
    type_3 = "type_3"
    type_2 = "type_2"
    type_1 = "type_1"


class Status(Enum):
    identified = "identified"
    unidentified = "unidentified"
    fire_not_caused_by_person = "fire_not_caused_by_person"


class PersonResponsible(BaseModel):
    """
    Person who caused the wildland fire, if any (NFIRS-8 L)
    """

    status: Optional[Status] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    activity: Optional[str] = None


class RightOfWay(BaseModel):
    """
    Nearby road/rail/power right-of-way (NFIRS-8 M)
    """

    row_type: Optional[str] = None
    distance_m: Optional[float] = None


class FireLines(BaseModel):
    primary_line_km: Optional[float] = None
    secondary_line_km: Optional[float] = None
    dozer_line_km: Optional[float] = None
    hand_line_km: Optional[float] = None


class AerialOperations(BaseModel):
    water_dropped_l: Optional[float] = None
    retardant_dropped_l: Optional[float] = None
    total_flight_hours: Optional[float] = None


class Wildland(BaseModel):
    is_wildland_incident: Optional[bool] = None
    discovery_datetime: Optional[AwareDatetime] = None
    area_type: Optional[AreaType] = None
    area_burned_ha: Optional[float] = None
    """
    Total area burned in hectares
    """
    land_ownership_breakdown: Optional[LandOwnershipBreakdown] = None
    percent_contained: Annotated[Optional[int], Field(None, ge=0, le=100)]
    fire_danger_rating: Optional[FireDangerRating] = None
    """
    Fire danger rating in effect at the time
    """
    fuel_model: Optional[str] = None
    """
    NFDRS or local fuel model at origin
    """
    fuel_moisture_percent: Optional[float] = None
    complexity_level: Optional[ComplexityLevel] = None
    """
    Incident complexity (type 5 lowest, type 1 highest)
    """
    slope_position: Optional[str] = None
    """
    Relative position on slope at origin
    """
    aspect: Optional[str] = None
    person_responsible: Optional[PersonResponsible] = None
    """
    Person who caused the wildland fire, if any (NFIRS-8 L)
    """
    right_of_way: Optional[RightOfWay] = None
    """
    Nearby road/rail/power right-of-way (NFIRS-8 M)
    """
    crops_burned: Optional[list[str]] = None
    fire_lines: Optional[FireLines] = None
    aerial_operations: Optional[AerialOperations] = None
    containment_strategies: Optional[list[str]] = None


class DamageRating(Enum):
    none = "none"
    minor = "minor"
    significant = "significant"
    heavy = "heavy"
    destroyed = "destroyed"
    undetermined = "undetermined"


class Exposure(BaseModel):
    """
    A property beyond the origin damaged or threatened by spread
    """

    exposure_number: Optional[int] = None
    """
    0 is the origin; exposures count up from 1 (NFIRS convention)
    """
    exposure_type: Optional[str] = None
    item_damaged: Optional[str] = None
    address: Optional[str] = None
    coordinates: Optional[Coordinates] = None
    property_use: Optional[str] = None
    people_present: Optional[bool] = None
    damage_rating: Optional[DamageRating] = None
    people_displaced: Optional[int] = None


class Affiliation(Enum):
    civilian = "civilian"
    ems_non_fd = "ems_non_fd"
    police = "police"
    other_responder = "other_responder"
    undetermined = "undetermined"


class HumanFactor1(Enum):
    asleep = "asleep"
    unconscious = "unconscious"
    impaired_by_alcohol = "impaired_by_alcohol"
    impaired_by_drugs = "impaired_by_drugs"
    mentally_disabled = "mentally_disabled"
    physically_disabled = "physically_disabled"
    physically_restrained = "physically_restrained"
    unattended_person = "unattended_person"
    other = "other"


class ActivityWhenInjured(Enum):
    escaping = "escaping"
    rescue_attempt = "rescue_attempt"
    fire_control = "fire_control"
    returning_before_control = "returning_before_control"
    returning_after_control = "returning_after_control"
    sleeping = "sleeping"
    unable_to_act = "unable_to_act"
    irrational_act = "irrational_act"
    other = "other"
    undetermined = "undetermined"


class LocationAtIgnition(Enum):
    in_area_of_origin = "in_area_of_origin"
    in_building_not_in_area = "in_building_not_in_area"
    outside_building = "outside_building"
    not_on_property = "not_on_property"
    undetermined = "undetermined"


class CareerOrVolunteer(Enum):
    career = "career"
    volunteer = "volunteer"
    undetermined = "undetermined"


class PhysicalConditionPrior(Enum):
    rested = "rested"
    fatigued = "fatigued"
    ill_or_injured = "ill_or_injured"
    other = "other"
    undetermined = "undetermined"


class WhereOccurred(Enum):
    enroute_to_scene = "enroute_to_scene"
    at_scene_inside = "at_scene_inside"
    at_scene_outside = "at_scene_outside"
    enroute_to_facility = "enroute_to_facility"
    at_facility = "at_facility"
    returning = "returning"
    at_station = "at_station"
    other = "other"
    undetermined = "undetermined"


class ProtectiveEquipmentFailure(BaseModel):
    failed: Optional[bool] = None
    item: Optional[str] = None
    problem: Optional[str] = None


class DutyStatus(Enum):
    on_duty = "on_duty"
    off_duty_responding = "off_duty_responding"
    off_duty = "off_duty"
    undetermined = "undetermined"


class TakenTo(Enum):
    hospital = "hospital"
    doctors_office = "doctors_office"
    morgue = "morgue"
    residence = "residence"
    station = "station"
    not_transported = "not_transported"
    other = "other"


class ResponderCasualty(BaseModel):
    personnel_id: Optional[str] = None
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    agency: Optional[str] = None
    role: Optional[str] = None
    rank: Optional[str] = None
    career_or_volunteer: Optional[CareerOrVolunteer] = None
    years_of_service: Optional[float] = None
    usual_assignment: Optional[str] = None
    physical_condition_prior: Optional[PhysicalConditionPrior] = None
    prior_responses_24h: Optional[int] = None
    injury_datetime: Optional[AwareDatetime] = None
    injury_type: Optional[str] = None
    primary_symptom: Optional[str] = None
    primary_body_part: Optional[str] = None
    severity: Optional[InjurySeverity] = None
    cause: Optional[str] = None
    contributing_factor: Optional[str] = None
    object_involved: Optional[str] = None
    activity_at_injury: Optional[str] = None
    where_occurred: Optional[WhereOccurred] = None
    story_where_injured: Optional[int] = None
    protective_equipment_failure: Optional[ProtectiveEquipmentFailure] = None
    duty_status: Optional[DutyStatus] = None
    treatment: Optional[str] = None
    taken_to: Optional[TakenTo] = None
    transported: Optional[bool] = None
    hospital: Optional[str] = None
    hospitalized_overnight: Optional[bool] = None
    return_to_duty_date: Optional[date_type] = None
    osha_recordable: Optional[bool] = None
    exposure_only: Optional[bool] = None
    """
    Chemical/biological exposure without immediate symptoms
    """


class PersonType(Enum):
    civilian = "civilian"
    firefighter = "firefighter"
    other_responder = "other_responder"


class RescueType(Enum):
    rescue = "rescue"
    assist = "assist"
    self_evacuation = "self_evacuation"
    body_recovery = "body_recovery"
    no_rescue_needed = "no_rescue_needed"


class RelativeTimeToSuppression(Enum):
    before_suppression = "before_suppression"
    during_suppression = "during_suppression"
    after_suppression = "after_suppression"
    undetermined = "undetermined"


class Mayday(BaseModel):
    """
    Firefighter emergencies only
    """

    called: Optional[bool] = None
    relative_time: Optional[str] = None
    rit_activated: Optional[bool] = None


class Rescue(BaseModel):
    """
    One person rescued, assisted or self-evacuated (NERIS rescue modules)
    """

    person_type: Optional[PersonType] = None
    rescue_type: Optional[RescueType] = None
    presence_known_beforehand: Optional[bool] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    primary_mode: Optional[str] = None
    """
    Primary rescue mode (interior search, ladder, water, rope, extrication)
    """
    actions: Optional[list[str]] = None
    impediments: Optional[list[str]] = None
    room_type: Optional[str] = None
    elevation: Optional[str] = None
    """
    Elevation at which the person was found (below grade, ground, upper story, roof)
    """
    removal_path: Optional[str] = None
    """
    Route used to remove the person (internal stairs, window, aerial)
    """
    relative_time_to_suppression: Optional[RelativeTimeToSuppression] = None
    gas_isolation: Optional[bool] = None
    """
    Space was isolated from heat/toxic gas flow
    """
    mayday: Optional[Mayday] = None
    """
    Firefighter emergencies only
    """
    resulting_casualty: Optional[bool] = None
    """
    True if this person also appears in casualties
    """


class EvacuationStatus(Enum):
    none = "none"
    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"
    repopulation_in_progress = "repopulation_in_progress"
    shelter_in_place = "shelter_in_place"


class EvacuationDisplacement(BaseModel):
    evacuation_occurred: Optional[bool] = None
    evacuation_status: Optional[EvacuationStatus] = None
    people_evacuated_without_assistance: Optional[int] = None
    people_evacuated_with_assistance: Optional[int] = None
    people_assisted_by_fd: Optional[int] = None
    total_people_evacuated: Optional[int] = None
    buildings_evacuated: Optional[int] = None
    evacuation_delay_reason: Optional[str] = None
    evacuation_completion_minutes: Optional[int] = None
    people_sheltering_in_place: Optional[int] = None
    people_in_temporary_shelters: Optional[int] = None
    people_trapped: Optional[int] = None
    people_missing: Optional[int] = None
    people_displaced: Optional[int] = None
    """
    People who cannot return to the property
    """
    displacement_causes: Optional[list[str]] = None


class InjuryIntent(Enum):
    accidental = "accidental"
    self_inflicted = "self_inflicted"
    inflicted_by_other = "inflicted_by_other"
    undetermined = "undetermined"


class BodySite(BaseModel):
    site: Optional[str] = None
    injury_type: Optional[str] = None


class CardiacArrest(BaseModel):
    occurred: Optional[bool] = None
    pre_arrival: Optional[bool] = None
    witnessed: Optional[bool] = None
    bystander_cpr: Optional[bool] = None
    initial_rhythm: Optional[str] = None


class HighestCareLevelOnScene(Enum):
    first_responder = "first_responder"
    emt_basic = "emt_basic"
    emt_intermediate = "emt_intermediate"
    paramedic = "paramedic"
    physician = "physician"
    other = "other"


class PatientStatus(Enum):
    improved = "improved"
    unchanged = "unchanged"
    worsened = "worsened"


class Disposition(Enum):
    treated_and_transported_by_fd = "treated_and_transported_by_fd"
    transported_by_other_agency = "transported_by_other_agency"
    treated_no_transport = "treated_no_transport"
    refused_care = "refused_care"
    dead_at_scene = "dead_at_scene"
    transferred_care = "transferred_care"
    other = "other"


class EMSPatient(BaseModel):
    """
    Summary-level patient record; the ePCR is the clinical record
    """

    patient_ref_id: Optional[str] = None
    nemsis_report_id: Optional[str] = None
    age_approx: Optional[int] = None
    date_of_birth: Optional[date_type] = None
    sex: Optional[str] = None
    chief_complaint: Optional[str] = None
    provider_impression: Optional[str] = None
    """
    Provider's primary impression/assessment
    """
    injury_intent: Optional[InjuryIntent] = None
    body_sites: Optional[list[BodySite]] = None
    """
    Injured body sites with injury type per site
    """
    procedures: Optional[list[str]] = None
    """
    Procedures performed on scene (CPR, oxygen, splinting, defibrillation)
    """
    cardiac_arrest: Optional[CardiacArrest] = None
    safety_equipment_used: Optional[list[str]] = None
    """
    Safety equipment used by the patient (seat belt, airbag, helmet)
    """
    highest_care_level_on_scene: Optional[HighestCareLevelOnScene] = None
    patient_status: Optional[PatientStatus] = None
    at_patient_datetime: Optional[AwareDatetime] = None
    transfer_of_care_datetime: Optional[AwareDatetime] = None
    disposition: Optional[Disposition] = None
    transported: Optional[bool] = None
    hospital_destination: Optional[str] = None


class IgnitionOrReleaseFirst(Enum):
    ignition_first = "ignition_first"
    release_first = "release_first"
    no_fire = "no_fire"
    undetermined = "undetermined"


class ReleaseCause(Enum):
    intentional = "intentional"
    unintentional = "unintentional"
    container_failure = "container_failure"
    act_of_nature = "act_of_nature"
    cause_under_investigation = "cause_under_investigation"
    undetermined = "undetermined"


class EquipmentInvolvedInRelease(BaseModel):
    involved: Optional[bool] = None
    equipment_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None


class Disposition1(Enum):
    """
    Who the cleanup/scene was released to. Evacuee counts live in evacuation_displacement.
    """

    completed_by_fire_service = "completed_by_fire_service"
    completed_with_fire_service_present = "completed_with_fire_service_present"
    released_to_local_agency = "released_to_local_agency"
    released_to_state_agency = "released_to_state_agency"
    released_to_federal_agency = "released_to_federal_agency"
    released_to_private_contractor = "released_to_private_contractor"
    released_to_owner = "released_to_owner"
    undetermined = "undetermined"


class PhysicalState(Enum):
    solid = "solid"
    liquid = "liquid"
    gas = "gas"
    undetermined = "undetermined"


class ReleasedInto(Enum):
    air = "air"
    water = "water"
    soil = "soil"
    contained_on_site = "contained_on_site"
    sewer_drain = "sewer_drain"
    other = "other"
    undetermined = "undetermined"


class HazmatMaterial(BaseModel):
    name: Optional[str] = None
    un_number: Optional[str] = None
    dot_hazard_class: Optional[str] = None
    """
    DOT/UN hazard class and division, e.g. "3" or "2.1"
    """
    cas_number: Optional[str] = None
    physical_state: Optional[PhysicalState] = None
    container_type: Optional[str] = None
    container_capacity: Optional[Quantity] = None
    released: Optional[bool] = None
    amount_released: Optional[Quantity] = None
    released_into: Optional[ReleasedInto] = None
    released_from_story: Optional[int] = None
    released_inside_structure: Optional[bool] = None


class Category1(Enum):
    battery_energy_storage = "battery_energy_storage"
    electric_vehicle = "electric_vehicle"
    micromobility_device = "micromobility_device"
    consumer_electronics = "consumer_electronics"
    photovoltaic_system = "photovoltaic_system"
    power_generation = "power_generation"
    csst_gas_tubing = "csst_gas_tubing"
    other = "other"


class SourceOrTarget(Enum):
    ignition_source = "ignition_source"
    target_only = "target_only"
    both = "both"
    undetermined = "undetermined"


class EmergingHazard(BaseModel):
    """
    Stored-energy and similar emerging hazards (NERIS emerging_hazard module)
    """

    category: Optional[Category1] = None
    subtype: Optional[str] = None
    source_or_target: Optional[SourceOrTarget] = None
    suppression_approach: Optional[str] = None
    reignition_occurred: Optional[bool] = None
    ev_crash_involved: Optional[bool] = None
    """
    Electric vehicle was involved in a crash
    """
    lightning_suspected: Optional[bool] = None
    """
    CSST cases, lightning as suspected cause
    """
    notes: Optional[str] = None


class CaseStatus(Enum):
    open = "open"
    closed_with_arrest = "closed_with_arrest"
    closed_exceptional = "closed_exceptional"
    closed = "closed"
    inactive = "inactive"


class AgencyReferredTo(BaseModel):
    name: Optional[str] = None
    case_number: Optional[str] = None


class IncendiaryDevice(BaseModel):
    container: Optional[str] = None
    ignition_delay_mechanism: Optional[str] = None
    fuel: Optional[str] = None


class MaterialAvailability(Enum):
    transported_to_scene = "transported_to_scene"
    available_at_scene = "available_at_scene"
    undetermined = "undetermined"


class Subject(BaseModel):
    age: Optional[int] = None
    sex: Optional[str] = None
    family_type: Optional[str] = None
    risk_factors: Optional[list[str]] = None
    disposition: Optional[str] = None


class JuvenileFiresetter(BaseModel):
    involved: Optional[bool] = None
    subjects: Optional[list[Subject]] = None


class Arson(BaseModel):
    suspected: Optional[bool] = None
    confirmed: Optional[bool] = None
    motivation_factors: Optional[list[str]] = None
    """
    Suspected motivations (fraud, intimidation, concealment, thrill, protest)
    """
    group_involvement: Optional[str] = None
    entry_method: Optional[str] = None
    extent_of_involvement_on_arrival: Optional[str] = None
    incendiary_device: Optional[IncendiaryDevice] = None
    material_availability: Optional[MaterialAvailability] = None
    initial_observations: Optional[list[str]] = None
    """
    Scene observations (forced entry, doors locked, security system state)
    """
    other_indicators: Optional[list[str]] = None
    """
    Contextual indicators (vacancy, for sale, insurance change, financial problems)
    """
    juvenile_firesetter: Optional[JuvenileFiresetter] = None


class Role(Enum):
    owner = "owner"
    occupant = "occupant"
    tenant = "tenant"
    reporting_party = "reporting_party"
    responsible_party = "responsible_party"
    witness = "witness"
    business_representative = "business_representative"
    insurance_holder = "insurance_holder"
    other = "other"


class Insurance(BaseModel):
    insured: Optional[bool] = None
    company: Optional[str] = None
    policy_number: Optional[str] = None


class PersonInvolved(BaseModel):
    """
    Owner, occupant or other party connected to the incident (not casualties)
    """

    role: Optional[Role] = None
    name: Optional[str] = None
    business_name: Optional[str] = None
    address: Optional[str] = None
    same_address_as_incident: Optional[bool] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    insurance: Optional[Insurance] = None


class Involvement(Enum):
    ignition_source_and_burned = "ignition_source_and_burned"
    ignition_source_not_burned = "ignition_source_not_burned"
    burned_not_ignition_source = "burned_not_ignition_source"
    collision = "collision"
    hazmat_release = "hazmat_release"
    rescued_from = "rescued_from"
    threatened_only = "threatened_only"
    other = "other"


class PropertyType(Enum):
    passenger_car = "passenger_car"
    motorcycle = "motorcycle"
    bus = "bus"
    heavy_goods_vehicle = "heavy_goods_vehicle"
    agricultural_vehicle = "agricultural_vehicle"
    construction_vehicle = "construction_vehicle"
    recreational_vehicle = "recreational_vehicle"
    train_rail = "train_rail"
    boat_vessel = "boat_vessel"
    aircraft = "aircraft"
    trailer = "trailer"
    mobile_home = "mobile_home"
    other = "other"


class FuelType(Enum):
    petrol_gasoline = "petrol_gasoline"
    diesel = "diesel"
    electric = "electric"
    hybrid = "hybrid"
    hydrogen = "hydrogen"
    cng_lpg = "cng_lpg"
    other = "other"
    undetermined = "undetermined"


class Extrication(BaseModel):
    """
    Extrication from this vehicle (UK IRS RTC block)
    """

    performed: Optional[bool] = None
    method: Optional[str] = None
    vehicle_position: Optional[str] = None
    time_taken_minutes: Optional[int] = None


class MobileProperty(BaseModel):
    involvement: Optional[Involvement] = None
    property_type: Optional[PropertyType] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    fuel_type: Optional[FuelType] = None
    license_plate: Optional[str] = None
    license_region: Optional[str] = None
    """
    Registering state/province/country
    """
    vin: Optional[str] = None
    dot_icc_number: Optional[str] = None
    reported_stolen: Optional[bool] = None
    appeared_abandoned: Optional[bool] = None
    occupants: Optional[int] = None
    extrication: Optional[Extrication] = None
    """
    Extrication from this vehicle (UK IRS RTC block)
    """


class EstimateMethod(Enum):
    rough_estimate = "rough_estimate"
    owner_estimate = "owner_estimate"
    insurance_assessment = "insurance_assessment"
    investigator_assessment = "investigator_assessment"
    official_valuation = "official_valuation"
    other = "other"


class Losses(BaseModel):
    """
    Monetary values. Currency follows the reporting agency.
    """

    no_loss: Optional[bool] = None
    property_loss: Optional[Money] = None
    contents_loss: Optional[Money] = None
    pre_incident_property_value: Optional[Money] = None
    pre_incident_contents_value: Optional[Money] = None
    property_saved: Optional[Money] = None
    other_costs: Optional[Money] = None
    estimate_method: Optional[EstimateMethod] = None


class WeatherType(Enum):
    clear = "clear"
    cloudy = "cloudy"
    rain = "rain"
    snow_ice = "snow_ice"
    fog = "fog"
    high_winds = "high_winds"
    thunderstorm_lightning = "thunderstorm_lightning"
    extreme_heat = "extreme_heat"
    extreme_cold = "extreme_cold"
    other = "other"


class WeatherReading(BaseModel):
    datetime: Optional[AwareDatetime] = None
    temperature_c: Optional[float] = None
    relative_humidity_percent: Optional[float] = None
    wind_speed_kph: Optional[float] = None
    wind_gusts_kph: Optional[float] = None
    wind_direction: Optional[str] = None
    haines_index: Optional[int] = None


class EnvironmentalImpact(BaseModel):
    habitat_affected_ha: Optional[float] = None
    watershed_impact: Optional[str] = None
    soil_erosion_risk: Optional[str] = None
    sensitive_species_affected: Optional[list[str]] = None
    air_quality_impact: Optional[str] = None
    water_body_affected: Optional[bool] = None


class InfrastructureItem(BaseModel):
    infrastructure_type: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[float] = None
    severity: Optional[str] = None


class NearMissEvent(BaseModel):
    description: Optional[str] = None
    date: Optional[date_type] = None
    contributing_factors: Optional[list[str]] = None
    lessons_learned: Optional[str] = None
    corrective_action: Optional[str] = None


class AttackType(Enum):
    verbal_abuse = "verbal_abuse"
    physical_no_weapon = "physical_no_weapon"
    weapon = "weapon"
    objects_thrown = "objects_thrown"
    vehicle_used = "vehicle_used"
    other = "other"


class AttacksOnPersonnel(BaseModel):
    """
    Attacks on responders travelling to, at, or from the incident (UK IRS 3.10-3.13)
    """

    occurred: Optional[bool] = None
    attack_type: Optional[AttackType] = None
    serious_injuries: Optional[int] = None
    slight_injuries: Optional[int] = None


class NearMissAndSafety(BaseModel):
    near_miss_events: Optional[list[NearMissEvent]] = None
    safety_breaches: Optional[int] = None
    maydays_count: Optional[int] = None
    attacks_on_personnel: Optional[AttacksOnPersonnel] = None
    """
    Attacks on responders travelling to, at, or from the incident (UK IRS 3.10-3.13)
    """
    weather_related_risks: Optional[list[str]] = None


class ReportVersion(Enum):
    initial = "initial"
    update = "update"
    final = "final"


class ComplexityLevel1(Enum):
    type_5 = "type_5"
    type_4 = "type_4"
    type_3 = "type_3"
    type_2 = "type_2"
    type_1 = "type_1"


class ThreatManagementEnum(Enum):
    no_likely_threat = "no_likely_threat"
    potential_future_threat = "potential_future_threat"
    mass_notifications_in_progress = "mass_notifications_in_progress"
    mass_notifications_completed = "mass_notifications_completed"
    no_evacuations_imminent = "no_evacuations_imminent"
    planning_for_evacuation = "planning_for_evacuation"
    planning_for_shelter_in_place = "planning_for_shelter_in_place"
    evacuations_in_progress = "evacuations_in_progress"
    shelter_in_place_in_progress = "shelter_in_place_in_progress"
    repopulation_in_progress = "repopulation_in_progress"
    area_restriction_in_effect = "area_restriction_in_effect"
    other = "other"


class ProjectedActivity(BaseModel):
    """
    Projected incident activity by timeframe
    """

    next_12_hours: Optional[str] = None
    next_24_hours: Optional[str] = None
    next_48_hours: Optional[str] = None
    next_72_hours: Optional[str] = None
    beyond_72_hours: Optional[str] = None


class SituationStatus(BaseModel):
    """
    Evolving large-incident status for sitreps (ICS-209 shape). Person counts
    live in casualties and evacuation_displacement; structure counts live in
    structure. Mappers compose the ICS-209 matrices from those sections.

    """

    report_version: Optional[ReportVersion] = None
    report_number: Optional[int] = None
    period_from: Optional[AwareDatetime] = None
    period_to: Optional[AwareDatetime] = None
    complexity_level: Optional[ComplexityLevel1] = None
    imt_type: Optional[str] = None
    """
    Incident management organization (single resource, type 3 IMT, unified command)
    """
    significant_events: Optional[str] = None
    primary_hazards: Optional[str] = None
    """
    Primary materials or hazards involved
    """
    threat_management: Optional[list[ThreatManagementEnum]] = None
    """
    Active protective actions
    """
    projected_activity: Optional[ProjectedActivity] = None
    """
    Projected incident activity by timeframe
    """
    strategic_objectives: Optional[str] = None
    threat_summary: Optional[str] = None
    critical_resource_needs: Optional[list[str]] = None
    planned_actions: Optional[str] = None
    projected_final_size_ha: Optional[float] = None
    anticipated_completion_date: Optional[date_type] = None
    demobilization_start_date: Optional[date_type] = None
    costs_to_date: Optional[Money] = None
    projected_final_cost: Optional[Money] = None


class LessonsLearned(BaseModel):
    successful_tactics: Optional[list[str]] = None
    areas_for_improvement: Optional[list[str]] = None
    recommendations: Optional[list[str]] = None


class MopUp(BaseModel):
    percent_complete: Optional[int] = None
    estimated_completion_date: Optional[date_type] = None
    personnel_assigned: Optional[int] = None


class Rehabilitation(BaseModel):
    erosion_control_ha: Optional[float] = None
    reseeding_ha: Optional[float] = None
    hazard_tree_removal_required: Optional[bool] = None


class FollowUp(BaseModel):
    mop_up: Optional[MopUp] = None
    rehabilitation: Optional[Rehabilitation] = None
    next_inspection_date: Optional[date_type] = None


class PeriodicReporting(BaseModel):
    contributes_to_monthly_report: Optional[bool] = None
    contributes_to_quarterly_report: Optional[bool] = None
    contributes_to_annual_report: Optional[bool] = None
    neris_submitted: Optional[bool] = None
    neris_submitted_at: Optional[AwareDatetime] = None
    state_submitted: Optional[bool] = None
    state_submitted_at: Optional[AwareDatetime] = None


class AttachmentRef(BaseModel):
    ref_id: Optional[UUID] = None
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None


class Attachments(BaseModel):
    maps: Optional[bool] = None
    photos_count: Optional[int] = None
    weather_charts: Optional[bool] = None
    resource_tracking_logs: Optional[bool] = None
    incident_action_plans: Optional[bool] = None
    attachment_refs: Optional[list[AttachmentRef]] = None


class ExtractionMetadata(BaseModel):
    extract_id: Optional[UUID] = None
    input_id: Optional[UUID] = None
    input_type: Optional[InputType] = None
    extracted_at: Optional[AwareDatetime] = None
    llm_model: Annotated[Optional[str], Field(None, examples=["llama3:8b"])]
    confidence_score: Annotated[Optional[float], Field(None, ge=0.0, le=1.0)]
    """
    Overall confidence score from the LLM extraction (0.0-1.0)
    """
    completeness: Optional[Completeness] = None


class SubmissionLogItem(BaseModel):
    form_type: Optional[FormType] = None
    submitted_at: Optional[AwareDatetime] = None
    submitted_to: Optional[str] = None


class ReportMetadata(BaseModel):
    report_id: Annotated[Optional[str], Field(None, examples=["FF-2024-CA-0157"])]
    incident_number: Annotated[Optional[str], Field(None, examples=["CA-SQF-2024-0421"])]
    """
    Department's own incident number
    """
    external_ids: Optional[list[ExternalId]] = None
    """
    Identifiers for this incident in external systems (CAD event, IRWIN, state registry, partner agency)
    """
    report_date: Optional[date_type] = None
    report_time: Optional[time_type] = None
    report_status: Optional[ReportStatus] = None
    reporting_unit: Optional[ReportingUnit] = None
    prepared_by: Optional[list[Personnel]] = None
    """
    Member(s) making the report
    """
    officer_in_charge: Optional[Personnel] = None
    reviewed_by: Optional[list[Reviewer]] = None
    submission_log: Optional[list[SubmissionLogItem]] = None


class IncidentType(BaseModel):
    primary: Optional[bool] = None
    """
    Only one entry may be primary
    """
    category: Optional[IncidentCategory] = None
    subcategory: Optional[str] = None
    """
    Free-form specific type within the category
    """
    codes: Optional[list[CodeRef]] = None
    """
    This type expressed in external coding schemes
    """


class RespondingAgencies(BaseModel):
    primary_agency: Optional[str] = None
    all_agencies: Optional[list[RespondingAgency]] = None
    mutual_aid_activated: Optional[bool] = None
    aid_direction: Optional[AidDirection] = None
    aid_type: Optional[AidType] = None
    non_fd_entities: Optional[list[str]] = None
    """
    Non fire department entities that assisted (utility, red cross, public works)
    """
    unified_command: Optional[bool] = None
    incident_commander: Optional[IncidentCommander] = None


class Fire(BaseModel):
    cause_category: Optional[CauseCategory] = None
    cause_specific: Optional[str] = None
    cause_codes: Optional[list[CodeRef]] = None
    cause_certainty: Optional[CauseCertainty] = None
    arson_suspected: Optional[bool] = None
    area_of_origin: Optional[str] = None
    """
    Room or area where the fire began
    """
    heat_source: Optional[str] = None
    """
    What provided the heat that started the fire
    """
    ignition_power_source: Optional[str] = None
    """
    What powered the ignition source (mains, battery, gas, open flame)
    """
    item_first_ignited: Optional[str] = None
    material_first_ignited: Optional[str] = None
    multiple_seats_of_fire: Optional[bool] = None
    """
    More than one independent point of origin (arson indicator)
    """
    human_factors: Optional[list[HumanFactor]] = None
    """
    Human factors contributing to ignition
    """
    person_involved_age: Optional[int] = None
    """
    Estimated age of person whose age was a factor
    """
    person_involved_sex: Optional[str] = None
    contributing_factors: Optional[list[str]] = None
    """
    Non-human factors contributing to ignition
    """
    equipment_involved: Optional[EquipmentInvolved] = None
    """
    Equipment involved in ignition, if any
    """
    on_site_materials: Optional[list[str]] = None
    """
    Significant commercial/industrial/agricultural materials on the property
    """
    fuel_types: Optional[list[str]] = None
    fire_spread_directions: Optional[list[str]] = None
    rate_of_spread: Optional[RateOfSpread] = None
    rate_of_spread_m_per_min: Optional[float] = None
    flame_length_m: Optional[float] = None
    spotting_distance_km: Optional[float] = None
    unusual_behaviors: Optional[list[str]] = None
    rapid_growth_cause: Optional[str] = None
    """
    Cause of any rapid fire growth (UK IRS 8.8)
    """
    fire_suppression_factors: Optional[list[str]] = None
    """
    Factors that helped or hindered suppression
    """
    suppression_operations: Optional[SuppressionOperations] = None


class CivilianCasualty(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    date_of_birth: Optional[date_type] = None
    sex: Optional[str] = None
    race_ethnicity: Optional[str] = None
    """
    Only where the target jurisdiction collects it (US, UK)
    """
    affiliation: Optional[Affiliation] = None
    injury_datetime: Optional[AwareDatetime] = None
    injury_type: Optional[str] = None
    """
    Nature of the injury (burns, smoke inhalation, trauma)
    """
    primary_symptom: Optional[str] = None
    primary_body_part: Optional[str] = None
    severity: Optional[InjurySeverity] = None
    cause: Optional[str] = None
    human_factors: Optional[list[HumanFactor1]] = None
    contributing_factors: Optional[list[str]] = None
    activity_when_injured: Optional[ActivityWhenInjured] = None
    location_at_ignition: Optional[LocationAtIgnition] = None
    story_at_start: Optional[int] = None
    story_where_injured: Optional[int] = None
    location_where_found: Optional[str] = None
    cause_of_failure_to_escape: Optional[str] = None
    """
    Why the person could not escape (Canada NFID casualty file)
    """
    disposition: Optional[str] = None
    transported: Optional[bool] = None
    hospital: Optional[str] = None
    fatal_circumstances: Optional[str] = None
    death_certificate_reconciled: Optional[bool] = None


class EMS(BaseModel):
    ems_response_required: Optional[bool] = None
    patients: Optional[list[EMSPatient]] = None
    total_patients: Optional[int] = None
    ems_agency_responded: Optional[str] = None
    nemsis_report_required: Optional[bool] = None
    nemsis_report_ids: Optional[list[str]] = None
    """
    Linked ePCR ids (NEMSIS eRecord.01); the full ePCR stays in the EMS system
    """


class Hazmat(BaseModel):
    involved: Optional[bool] = None
    materials: Optional[list[HazmatMaterial]] = None
    ignition_or_release_first: Optional[IgnitionOrReleaseFirst] = None
    release_cause: Optional[ReleaseCause] = None
    release_factors: Optional[list[str]] = None
    mitigation_factors: Optional[list[str]] = None
    """
    Factors or impediments that affected mitigation
    """
    actions_taken: Optional[list[str]] = None
    """
    Hazmat-specific actions (identification, containment, decontamination, neutralization)
    """
    equipment_involved_in_release: Optional[EquipmentInvolvedInRelease] = None
    area_affected: Optional[Quantity] = None
    area_evacuated: Optional[Quantity] = None
    epa_reportable_quantity_exceeded: Optional[bool] = None
    disposition: Optional[Disposition1] = None
    """
    Who the cleanup/scene was released to. Evacuee counts live in evacuation_displacement.
    """


class Investigation(BaseModel):
    investigation_needed: Optional[bool] = None
    """
    Incident commander's assessment that formal investigation is required
    """
    investigation_types: Optional[list[str]] = None
    """
    Types of investigation completed (origin_and_cause, arson, insurance, forensic)
    """
    investigation_ongoing: Optional[bool] = None
    case_status: Optional[CaseStatus] = None
    agency_referred_to: Optional[AgencyReferredTo] = None
    law_enforcement_notified: Optional[bool] = None
    evidence_collected: Optional[bool] = None
    laboratory_used: Optional[str] = None
    nibrs_report_required: Optional[bool] = None
    arson: Optional[Arson] = None
    notes: Optional[str] = None


class Weather(BaseModel):
    on_arrival: Optional[WeatherReading] = None
    worst_conditions: Optional[WeatherReading] = None
    weather_type: Optional[WeatherType] = None
    factors_influencing_fire: Optional[list[str]] = None


class InfrastructureImpact(BaseModel):
    items: Optional[list[InfrastructureItem]] = None


class Incident(BaseModel):
    name: Optional[str] = None
    """
    Human-readable incident name
    """
    types: Optional[list[IncidentType]] = None
    special_modifiers: Annotated[
        Optional[list[str]], Field(None, examples=[["mass_casualty", "major_incident"]])
    ]
    """
    Magnitude or class tags qualifying the incident (NERIS special modifiers)
    """
    false_alarm: Optional[FalseAlarm] = None
    """
    Populated when the final type is a false alarm
    """
    special_service_type: Optional[str] = None
    """
    Non-fire service call subtype (lift release, lock-in, flooding, animal assist, co-response)
    """
    chimney_fire: Optional[bool] = None
    """
    Flame confined to a chimney (UK IRS 3.9)
    """
    timezone: Annotated[Optional[str], Field(None, examples=["America/Los_Angeles"])]
    """
    IANA timezone of the incident, for local wall-clock rendering
    """
    discovered_datetime: Optional[AwareDatetime] = None
    how_discovered: Optional[str] = None
    """
    How the fire or emergency was first discovered
    """
    delay_ignition_to_discovery: Optional[DelayIgnitionToDiscovery] = None
    delay_discovery_to_call: Optional[DelayDiscoveryToCall] = None
    start_datetime: Optional[AwareDatetime] = None
    """
    Estimated ignition or emergency start
    """
    alarm_datetime: Optional[AwareDatetime] = None
    """
    Department alerted / alarm time
    """
    first_arrival_datetime: Optional[AwareDatetime] = None
    """
    First unit on scene
    """
    command_established_datetime: Optional[AwareDatetime] = None
    sizeup_complete_datetime: Optional[AwareDatetime] = None
    water_on_fire_datetime: Optional[AwareDatetime] = None
    primary_search_begin_datetime: Optional[AwareDatetime] = None
    primary_search_complete_datetime: Optional[AwareDatetime] = None
    knocked_down_datetime: Optional[AwareDatetime] = None
    containment_datetime: Optional[AwareDatetime] = None
    controlled_datetime: Optional[AwareDatetime] = None
    extrication_complete_datetime: Optional[AwareDatetime] = None
    suppression_complete_datetime: Optional[AwareDatetime] = None
    loss_stopped_datetime: Optional[AwareDatetime] = None
    stop_message_datetime: Optional[AwareDatetime] = None
    """
    Stop / situation-under-control message to control room (UK IRS 2.5)
    """
    cleared_datetime: Optional[AwareDatetime] = None
    """
    Last unit cleared the scene
    """
    closed_datetime: Optional[AwareDatetime] = None
    """
    Incident administratively closed
    """
    total_duration_hours: Optional[float] = None
    alarm_level: Optional[int] = None
    """
    Number of alarms / escalation level
    """
    shift_or_platoon: Optional[str] = None
    district: Optional[str] = None
    """
    Response district or box area
    """
    people_present: Optional[bool] = None
    """
    Whether people were present at the location at the time
    """
    animals_rescued: Optional[int] = None
    animals_deceased: Optional[int] = None
    narrative: Optional[str] = None
    """
    Free text summary of the incident
    """
    narrative_impediment: Optional[str] = None
    """
    Obstacles that impacted the response (NERIS)
    """
    narrative_outcome: Optional[str] = None
    """
    Final disposition of the incident (NERIS)
    """
    raw_transcript: Optional[str] = None
    """
    Original voice or text input verbatim
    """


class Casualties(BaseModel):
    """
    Injuries and deaths. Uninjured rescues live in rescues[].
    """

    civilian: Optional[list[CivilianCasualty]] = None
    responder: Optional[list[ResponderCasualty]] = None
    total_civilian_injuries: Optional[int] = None
    total_civilian_fatalities: Optional[int] = None
    total_responder_injuries: Optional[int] = None
    total_responder_fatalities: Optional[int] = None


class IncidentContract(BaseModel):
    """
    The FireForm incident contract. This is the superset schema
    containing every field any downstream form could need. Form-specific
    mappers select only the relevant fields for each agency template.
    Stored as a single JSONB document; queryable stats are promoted to
    IncidentRecord columns server-side.

    """

    schema_version: Annotated[Optional[str], Field(None, examples=["1.1.0"])]
    """
    Schema version identifier
    """
    schema_name: Optional[SchemaName] = None
    """
    Schema name identifier
    """
    extraction_metadata: Optional[ExtractionMetadata] = None
    report_metadata: Optional[ReportMetadata] = None
    incident: Optional[Incident] = None
    dispatch: Optional[Dispatch] = None
    location: Optional[Location] = None
    actions_taken: Optional[ActionsTaken] = None
    responding_agencies: Optional[RespondingAgencies] = None
    units: Optional[list[UnitResponse]] = None
    """
    Per-unit (apparatus/resource) response records with timestamps
    """
    resources_summary: Optional[ResourcesSummary] = None
    fire: Optional[Fire] = None
    explosion: Optional[Explosion] = None
    risk_reduction: Optional[RiskReduction] = None
    structure: Optional[Structure] = None
    wildland: Optional[Wildland] = None
    exposures: Optional[list[Exposure]] = None
    """
    Properties beyond the origin affected by spread of the incident
    """
    casualties: Optional[Casualties] = None
    rescues: Optional[list[Rescue]] = None
    """
    Rescues and assisted evacuations, with or without injury
    """
    evacuation_displacement: Optional[EvacuationDisplacement] = None
    ems: Optional[EMS] = None
    hazmat: Optional[Hazmat] = None
    emerging_hazards: Optional[list[EmergingHazard]] = None
    """
    Battery, EV, solar and other stored-energy hazards (NERIS)
    """
    investigation: Optional[Investigation] = None
    persons_involved: Optional[list[PersonInvolved]] = None
    """
    Owners, occupants and other parties connected to the incident
    """
    mobile_property: Optional[list[MobileProperty]] = None
    """
    Vehicles, vessels and other mobile property involved
    """
    losses: Optional[Losses] = None
    weather: Optional[Weather] = None
    environmental_impact: Optional[EnvironmentalImpact] = None
    infrastructure_impact: Optional[InfrastructureImpact] = None
    near_miss_and_safety: Optional[NearMissAndSafety] = None
    situation_status: Optional[SituationStatus] = None
    lessons_learned: Optional[LessonsLearned] = None
    follow_up: Optional[FollowUp] = None
    periodic_reporting: Optional[PeriodicReporting] = None
    attachments: Optional[Attachments] = None
    custom_fields: Optional[dict[str, Any]] = None
    """
    Agency-local fields with no contract home (NFIRS special studies,
    IRS local options and similar). Keys are agency-defined strings,
    values are scalars. Passed through to mappers untouched.

    """
