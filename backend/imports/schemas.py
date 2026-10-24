"""Import contract: upload (or load the sample) -> map columns and values -> preview -> commit (a background job).

The frontend flow: `uploadImport` / `loadSampleImport` -> `getImport` (columns with guesses, distinct status
values) -> `setImportMapping` (returns the refreshed preview) -> `commitImport` (202) -> poll `getImport` until
`status` is `committed` or `failed`. `getImportPreview` after commit shows what commit did.
"""

from datetime import date, datetime
from typing import Literal

from ninja import Schema
from pydantic import Field

from core.domain import DecisionOutcome, ItemStatus
from imports.domain import (
    ImportProblemKind,
    ImportStatus,
    ImportTargetField,
    ImportValueField,
    ProblemSeverity,
    RowAction,
)
from reviews.schemas import PartyRefOut


class ImportSummaryOut(Schema):
    created: int
    skipped: int
    partners_created: int


class ImportJobSummaryOut(Schema):
    id: int
    status: ImportStatus
    filename: str
    sheet_name: str
    row_count: int = Field(description="Sheet rows below the header, data or not.")
    created_by: PartyRefOut
    created_at: datetime
    updated_at: datetime
    commit_requested_at: datetime | None
    committed_at: datetime | None
    summary: ImportSummaryOut | None = Field(description="Set once committed.")
    error: str | None = Field(description="Why the last commit failed, if it did.")


class ImportColumnOut(Schema):
    name: str
    sample_values: list[str]
    suggested_field: ImportTargetField | None
    field: ImportTargetField = Field(description="What the column is mapped to now.")


class StatusValueOut(Schema):
    source_value: str
    rows: int
    status: ItemStatus | None = Field(description="Null until mapped: the row can't be imported.")
    outcome: DecisionOutcome | None
    source: Literal["default", "mapped"] | None = Field(
        description="default: the built-in table; mapped: the admin's mapping; null: not mapped yet."
    )


class ValueMappingOut(Schema):
    field: ImportValueField
    source_value: str
    value: str


class ImportJobOut(ImportJobSummaryOut):
    columns: list[ImportColumnOut]
    status_values: list[StatusValueOut] = Field(description="Distinct values in the mapped status column.")
    value_mappings: list[ValueMappingOut]


class ColumnMappingIn(Schema):
    source: str = Field(description="A header from the sheet.")
    target: ImportTargetField


class StatusMappingIn(Schema):
    source_value: str = Field(min_length=1, max_length=200)
    status: ItemStatus
    outcome: DecisionOutcome | None = Field(default=None, description="Defaults to the decision the status implies.")


class ValueMappingIn(Schema):
    field: ImportValueField
    source_value: str = Field(min_length=1, max_length=200)
    value: str = Field(
        min_length=1,
        max_length=200,
        description="product/channel/risk_tier: the app value; partner: a partner name; trigger_terms: yes or no.",
    )


class ImportMappingIn(Schema):
    """`columns` are merged into the current mapping (headers left out keep theirs). `status_values` and
    `value_mappings` replace the saved lists when sent; leave them out (or null) to keep what's saved."""

    columns: list[ColumnMappingIn] = Field(default_factory=list)
    status_values: list[StatusMappingIn] | None = None
    value_mappings: list[ValueMappingIn] | None = None


class ImportProblemOut(Schema):
    row_number: int | None = Field(description="Excel's row number; null for a problem with the whole sheet.")
    column: str | None
    kind: ImportProblemKind
    severity: ProblemSeverity = Field(
        description="error: the row is skipped (or blocks commit); warning: imported, worth a look; info: a value "
        "read from a non-standard form."
    )
    value: str | None
    message: str


class UnmappedValueOut(Schema):
    field: ImportTargetField
    value: str
    rows: int


class ImportCountsOut(Schema):
    rows_total: int
    ready: int = Field(description="Rows commit creates an item for (or created, once committed).")
    duplicates: int
    already_imported: int
    not_data: int
    blocked: int = Field(description="Rows with an error-severity problem.")


class ImportPreviewRowOut(Schema):
    row_number: int
    action: RowAction
    legacy_ref: str | None
    title: str | None
    status: ItemStatus | None
    outcome: DecisionOutcome | None
    submitted_on: date | None
    partner: str | None
    problem_count: int


class ImportPreviewOut(Schema):
    job_id: int
    status: ImportStatus
    counts: ImportCountsOut
    problems: list[ImportProblemOut]
    unmapped: list[UnmappedValueOut] = Field(description="Values the admin must map before those rows import.")
    rows: list[ImportPreviewRowOut]


class ImportCommitIn(Schema):
    skip_rows_with_problems: bool = Field(
        default=True, description="Skip rows with error-severity problems; false refuses to commit while any exist."
    )
