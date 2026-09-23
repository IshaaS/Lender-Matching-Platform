from enum import StrEnum


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDERWRITING = "underwriting"
    COMPLETED = "completed"


class TransactionType(StrEnum):
    DEALER_PURCHASE = "dealer_purchase"
    PRIVATE_PARTY = "private_party"
    SALE_LEASEBACK = "sale_leaseback"
    REFINANCE = "refinance"


class EquipmentCondition(StrEnum):
    NEW = "new"
    USED = "used"


class PolicyStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunMode(StrEnum):
    HATCHET = "hatchet"
    SYNC = "sync"


class MatchStatus(StrEnum):
    EVALUATED = "evaluated"
    ERROR = "error"


class IngestionStatus(StrEnum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    DRAFT_READY = "draft_ready"
    FAILED = "failed"
