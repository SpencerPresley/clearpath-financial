"""Export contract. Files are built in the background: `createExport` / `createEvidencePack` return 202 with a
job; poll `getExport` until `status` is `ready` (then follow `download_url`) or `failed`."""

from datetime import datetime

from ninja import Schema
from pydantic import Field

from checks.schemas import FindingOut
from exports.domain import ExportKind, ExportStatus
from reviews.filters import ItemFilter, ItemSort
from reviews.schemas import DecisionOut, EvidenceOut, ItemRowOut, VersionOut
from terms.schemas import OfferTermsOut


class ExportIn(Schema):
    """Export any filtered view as xlsx, in the view's sort order."""

    filters: ItemFilter = Field(default_factory=ItemFilter)
    sort: ItemSort = ItemSort.NEWEST
    include_evidence_packs: bool = Field(
        default=False,
        description="Return a zip: the xlsx plus an evidence pack for every item in the view with an approval "
        "(at most 200).",
    )


class ExportOut(Schema):
    id: int
    kind: ExportKind
    status: ExportStatus
    item_id: int | None = Field(description="The item, for an evidence pack.")
    item_count: int | None = Field(description="Rows in the file; set once ready.")
    filename: str | None
    download_url: str | None = Field(description="Set once status is ready. Only the requester can download.")
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class EvidencePackOut(Schema):
    """What an approval was recorded against: the approved version, the decision and the findings triaged on
    that version, the terms it quotes, and the evidence it relied on, by hash. The zip
    (`createEvidencePack`) holds the same record plus the files and the item history."""

    item: ItemRowOut
    approved_version: VersionOut
    decision: DecisionOut
    findings: list[FindingOut]
    offer_terms: list[OfferTermsOut]
    evidence: list[EvidenceOut]
    generated_at: datetime
