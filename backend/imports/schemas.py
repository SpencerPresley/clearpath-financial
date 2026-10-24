"""Import contract: upload (or load the sample) -> map columns -> map status values -> preview -> commit.
Workstream G owns behavior and models; refine these with samples/README.md's list of intended messes."""

from datetime import datetime

from ninja import Schema
from pydantic import Field

from core.domain import DecisionOutcome, ItemStatus
from imports.domain import ImportProblemKind, ImportStatus, ImportTargetField
from reviews.schemas import PartyRefOut


class ImportColumnOut(Schema):
    name: str
    sample_values: list[str]
    suggested_field: ImportTargetField | None


class ColumnMappingOut(Schema):
    source: str
    target: ImportTargetField


class StatusMappingOut(Schema):
    source_value: str
    status: ItemStatus
    outcome: DecisionOutcome | None = Field(default=None, description="The decision implied, if any.")


class ImportJobOut(Schema):
    id: int
    status: ImportStatus
    filename: str
    sheet_name: str
    row_count: int
    columns: list[ImportColumnOut]
    status_values: list[str] = Field(description="Distinct values found in the mapped status column.")
    column_mapping: list[ColumnMappingOut]
    status_mapping: list[StatusMappingOut]
    created_by: PartyRefOut
    created_at: datetime


class ColumnMappingIn(Schema):
    source: str
    target: ImportTargetField


class StatusMappingIn(Schema):
    source_value: str
    status: ItemStatus
    outcome: DecisionOutcome | None = None


class ImportMappingIn(Schema):
    columns: list[ColumnMappingIn] = Field(min_length=1)
    status_values: list[StatusMappingIn] = Field(default_factory=list)


class ImportProblemOut(Schema):
    row_number: int = Field(description="1-based row number in the sheet, as the admin sees it in Excel.")
    column: str | None
    kind: ImportProblemKind
    value: str | None
    message: str


class ImportPreviewRowOut(Schema):
    row_number: int
    legacy_ref: str | None
    title: str | None
    status: ItemStatus | None
    submitted_on: datetime | None
    ok: bool


class ImportPreviewOut(Schema):
    job_id: int
    rows_total: int
    rows_ready: int
    rows_with_problems: int
    problems: list[ImportProblemOut]
    sample_rows: list[ImportPreviewRowOut]


class ImportCommitIn(Schema):
    skip_rows_with_problems: bool = True


class ImportCommitOut(Schema):
    job_id: int
    created: int
    skipped: int
