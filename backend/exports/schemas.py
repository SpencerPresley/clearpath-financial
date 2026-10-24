from datetime import datetime
from enum import StrEnum

from ninja import Schema
from pydantic import Field

from reviews.filters import ItemFilter
from reviews.schemas import DecisionOut, EvidenceOut, ItemRowOut, VersionOut
from terms.schemas import OfferTermsOut


class ExportKind(StrEnum):
    ITEMS_XLSX = "items_xlsx"
    EVIDENCE_PACK = "evidence_pack"


class ExportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class ExportIn(Schema):
    """Export any filtered view: an xlsx index, plus an evidence pack per approved item if asked."""

    filters: ItemFilter
    include_evidence_packs: bool = False


class ExportOut(Schema):
    id: int
    status: ExportStatus
    item_count: int | None
    download_url: str | None = Field(description="Set once status is ready.")
    error: str | None
    created_at: datetime


class EvidencePackOut(Schema):
    """What an approval was recorded against: the approved version, the decision, the terms it quotes, and
    the evidence it relied on, by hash."""

    item: ItemRowOut
    approved_version: VersionOut
    decision: DecisionOut
    offer_terms: list[OfferTermsOut]
    evidence: list[EvidenceOut]
    generated_at: datetime
