"""Export vocabulary shared by models, services, and schemas."""

from enum import StrEnum


class ExportKind(StrEnum):
    ITEMS_XLSX = "items_xlsx"
    EVIDENCE_PACK = "evidence_pack"


class ExportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
