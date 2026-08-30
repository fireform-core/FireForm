from enum import Enum


class InputType(str, Enum):
    voice = "voice"
    text = "text"


class InputStatus(str, Enum):
    queued = "queued"
    transcribing = "transcribing"
    ready = "ready"
    failed = "failed"


class ExtractionStatus(str, Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"
    needs_review = "needs_review"


class FormStatus(str, Enum):
    queued = "queued"
    generating = "generating"
    completed = "completed"
    failed = "failed"


class ReportStatus(str, Enum):
    draft = "draft"
    under_review = "under_review"
    approved = "approved"
    submitted = "submitted"


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobType(str, Enum):
    transcription = "transcription"
    extraction = "extraction"
    form_generation = "form_generation"
    batch_form_generation = "batch_form_generation"
    report_generation = "report_generation"
    template_field_detection = "template_field_detection"


class FormType(str, Enum):
    neris = "neris"
    nemsis_epcr = "nemsis_epcr"
    nibrs = "nibrs"
    nfirs_basic = "nfirs_basic"
    nfirs_fire = "nfirs_fire"
    nfirs_structure = "nfirs_structure"
    nfirs_wildland = "nfirs_wildland"
    nfirs_ems = "nfirs_ems"
    nfirs_hazmat = "nfirs_hazmat"
    nfirs_apparatus = "nfirs_apparatus"
    nfirs_personnel = "nfirs_personnel"
    nfirs_arson = "nfirs_arson"
    nfirs_casualty_civilian = "nfirs_casualty_civilian"
    nfirs_casualty_responder = "nfirs_casualty_responder"
    cal_fire_ics209 = "cal_fire_ics209"
    osha_301 = "osha_301"
    un_ssirs = "un_ssirs"
    state_georgia = "state_georgia"
    state_california = "state_california"
    state_new_york = "state_new_york"


class DetectionStatus(str, Enum):
    """Field-detection state of an uploaded template PDF. The PDF itself is
    stored before any of this runs, so a failed detection is recoverable."""

    processing = "processing"
    completed = "completed"
    failed = "failed"


class TemplateStatus(str, Enum):
    active = "active"
    legacy = "legacy"
    draft = "draft"


class TextAlign(str, Enum):
    left = "left"
    center = "center"
    right = "right"


class TemplateFieldType(str, Enum):
    string = "string"
    integer = "integer"
    number = "number"
    boolean = "boolean"
    date = "date"
    datetime = "datetime"
    time = "time"
    enum = "enum"
    text = "text"
    array = "array"


class IncidentCategory(str, Enum):
    fire = "fire"
    overpressure_explosion = "overpressure_explosion"
    ems = "ems"
    rescue = "rescue"
    hazardous_conditions = "hazardous_conditions"
    service_call = "service_call"
    good_intent = "good_intent"
    false_alarm = "false_alarm"
    natural_disaster = "natural_disaster"
    law_enforcement = "law_enforcement"
    special_incident = "special_incident"


class CauseCertainty(str, Enum):
    confirmed = "confirmed"
    probable = "probable"
    suspected = "suspected"
    undetermined = "undetermined"


class InjurySeverity(str, Enum):
    minor = "minor"
    moderate = "moderate"
    severe = "severe"
    life_threatening = "life_threatening"
    fatal = "fatal"
    undetermined = "undetermined"


class RateOfSpread(str, Enum):
    slow = "slow"
    moderate = "moderate"
    rapid = "rapid"
    extreme = "extreme"


class PeriodType(str, Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"


class OutputFormat(str, Enum):
    pdf = "pdf"
    json = "json"
    both = "both"


class FieldSource(str, Enum):
    schema = "schema"
    static = "static"
    manual = "manual"
    open = "open"
