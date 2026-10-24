"""Import vocabulary: plain enums shared by the parser, the services, and the API schemas."""

from enum import StrEnum


class ImportStatus(StrEnum):
    UPLOADED = "uploaded"
    MAPPED = "mapped"
    COMMITTING = "committing"
    COMMITTED = "committed"
    FAILED = "failed"


class ImportTargetField(StrEnum):
    """What a tracker column maps onto."""

    LEGACY_REF = "legacy_ref"
    SUBMITTED_ON = "submitted_on"
    SUBMITTER = "submitter"
    PRODUCT = "product"
    CHANNEL = "channel"
    TITLE = "title"
    PARTNER = "partner"
    RISK_TIER = "risk_tier"
    TRIGGER_TERMS = "trigger_terms"
    REVIEWER = "reviewer"
    VERSION_NUMBER = "version_number"
    ROUNDS = "rounds"
    STATUS = "status"
    COMMENTS = "comments"
    APPROVAL = "approval"
    EXPIRES_ON = "expires_on"
    PLACEMENT = "placement"
    NOTES = "notes"
    IGNORE = "ignore"


class ImportValueField(StrEnum):
    """Columns whose raw values map onto app values; unknown ones are listed for the admin to map."""

    PRODUCT = "product"
    CHANNEL = "channel"
    RISK_TIER = "risk_tier"
    PARTNER = "partner"
    TRIGGER_TERMS = "trigger_terms"


class ProblemSeverity(StrEnum):
    """error: the row can't be imported as is. warning: imported, but someone should look. info: a value was
    read from a non-standard form (a date typed as text)."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ImportProblemKind(StrEnum):
    MISSING_MAPPING = "missing_mapping"
    MISSING_VALUE = "missing_value"
    UNPARSEABLE_DATE = "unparseable_date"
    COERCED_DATE = "coerced_date"
    UNMAPPED_STATUS = "unmapped_status"
    INFERRED_STATUS = "inferred_status"
    UNKNOWN_VALUE = "unknown_value"
    UNKNOWN_PARTNER = "unknown_partner"
    FUZZY_PARTNER = "fuzzy_partner"
    MISSING_EXPIRY = "missing_expiry"
    UNKNOWN_TRIGGER_TERMS = "unknown_trigger_terms"
    DERIVED_APPROVAL_DATE = "derived_approval_date"
    UNRESOLVED_APPROVER = "unresolved_approver"
    INCONSISTENT_DATES = "inconsistent_dates"
    DUPLICATE_ROW = "duplicate_row"
    REUSED_REF = "reused_ref"
    ALREADY_IMPORTED = "already_imported"
    NOT_DATA_ROW = "not_data_row"


class RowAction(StrEnum):
    """What commit does with a row."""

    CREATE = "create"
    SKIP_DUPLICATE = "skip_duplicate"
    SKIP_ALREADY_IMPORTED = "skip_already_imported"
    SKIP_NOT_DATA = "skip_not_data"
    BLOCKED = "blocked"  # has an error-severity problem
