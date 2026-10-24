"""Reads for the Import page. Admins only, like every import action."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal

from django.db.models import QuerySet
from pydantic import TypeAdapter

from accounts.models import User
from core.domain import DecisionOutcome, ItemStatus, Role
from core.errors import NotFound
from core.permissions import require_role
from imports.domain import ImportStatus, ImportTargetField, ImportValueField, RowAction
from imports.mapping import DEFAULT_STATUS_MAP, guess_target, value_key
from imports.models import ImportJob, ImportRow
from imports.normalize import ImportCounts, ParsedRow, Problem, UnmappedValue
from imports.services import evaluate, job_mapping, job_workbook
from reviews.selectors import PartyRef

_PARSED_ROW: Final = TypeAdapter(ParsedRow)
_SAMPLE_VALUES: Final = 3


@dataclass(frozen=True)
class ImportSummary:
    created: int
    skipped: int
    partners_created: int


@dataclass(frozen=True)
class ImportJobRow:
    id: int
    status: ImportStatus
    filename: str
    sheet_name: str
    row_count: int
    created_by: PartyRef
    created_at: datetime
    updated_at: datetime
    commit_requested_at: datetime | None
    committed_at: datetime | None
    summary: ImportSummary | None  # set once committed
    error: str | None


@dataclass(frozen=True)
class ImportColumn:
    name: str
    sample_values: tuple[str, ...]
    suggested_field: ImportTargetField | None
    field: ImportTargetField  # what it is mapped to now


@dataclass(frozen=True)
class StatusValue:
    """A distinct value in the mapped Status column and what it imports as. `source` says where that came
    from: the built-in table, the admin, or nowhere yet (the admin must map it)."""

    source_value: str
    rows: int
    status: ItemStatus | None
    outcome: DecisionOutcome | None
    source: Literal["default", "mapped"] | None


@dataclass(frozen=True)
class ValueMapping:
    field: ImportValueField
    source_value: str
    value: str


@dataclass(frozen=True)
class ImportJobDetail(ImportJobRow):
    columns: tuple[ImportColumn, ...]
    status_values: tuple[StatusValue, ...]
    value_mappings: tuple[ValueMapping, ...]


@dataclass(frozen=True)
class PreviewRow:
    row_number: int
    action: RowAction
    legacy_ref: str | None
    title: str | None
    status: ItemStatus | None
    outcome: DecisionOutcome | None
    submitted_on: date | None
    partner: str | None
    problem_count: int
    item_id: int | None  # the item commit created from this row; null before commit and for skipped rows


@dataclass(frozen=True)
class ImportPreview:
    """Rows and problems as commit would see them now; once committed, what commit did."""

    job_id: int
    status: ImportStatus
    counts: ImportCounts
    problems: tuple[Problem, ...]
    unmapped: tuple[UnmappedValue, ...]
    rows: tuple[PreviewRow, ...]


def _jobs() -> QuerySet[ImportJob]:
    return ImportJob.objects.select_related("created_by").defer("workbook")


def _job(job_id: int) -> ImportJob:
    job = ImportJob.objects.select_related("created_by").filter(pk=job_id).first()
    if job is None:
        raise NotFound.entity("import", job_id)
    return job


def _row(job: ImportJob) -> ImportJobRow:
    committed = job.status == ImportStatus.COMMITTED.value
    by = job.created_by
    return ImportJobRow(
        id=job.pk,
        status=ImportStatus(job.status),
        filename=job.filename,
        sheet_name=job.sheet_name,
        row_count=job.row_count,
        created_by=PartyRef(id=by.pk, name=by.display_name or by.email),
        created_at=job.created_at,
        updated_at=job.updated_at,
        commit_requested_at=job.commit_requested_at,
        committed_at=job.committed_at,
        summary=ImportSummary(job.created_count, job.skipped_count, job.partners_created_count) if committed else None,
        error=job.error or None,
    )


def list_imports(*, viewer: User, limit: int = 20) -> tuple[ImportJobRow, ...]:
    require_role(viewer, Role.ADMIN)
    return tuple(_row(j) for j in _jobs().order_by("-created_at", "-pk")[:limit])


def _status_values(job: ImportJob) -> tuple[StatusValue, ...]:
    sheet, mapping = job_workbook(job).tracker, job_mapping(job)
    index = next((i for i, h in enumerate(sheet.headers) if mapping.columns.get(h) is ImportTargetField.STATUS), None)
    if index is None:
        return ()
    overrides = {value_key(o.source_value): o for o in mapping.statuses}
    counts = Counter(v for r in sheet.rows if (v := r.cells[index].display))
    out = []
    for raw, n in sorted(counts.items()):
        key = value_key(raw)
        if key in overrides:
            o = overrides[key]
            out.append(StatusValue(raw, n, o.status, o.outcome, "mapped"))
        elif key in DEFAULT_STATUS_MAP:
            d = DEFAULT_STATUS_MAP[key]
            out.append(StatusValue(raw, n, d.status, d.outcome, "default"))
        else:
            out.append(StatusValue(raw, n, None, None, None))
    return tuple(out)


def get_import(*, viewer: User, job_id: int) -> ImportJobDetail:
    require_role(viewer, Role.ADMIN)
    job = _job(job_id)
    sheet, mapping = job_workbook(job).tracker, job_mapping(job)
    columns = tuple(
        ImportColumn(
            name=header,
            sample_values=tuple(dict.fromkeys(v for r in sheet.rows if (v := r.cells[i].display)))[:_SAMPLE_VALUES],
            suggested_field=guess_target(header),
            field=mapping.columns.get(header, ImportTargetField.IGNORE),
        )
        for i, header in enumerate(sheet.headers)
    )
    row = _row(job)
    return ImportJobDetail(
        **{f: getattr(row, f) for f in ImportJobRow.__dataclass_fields__},
        columns=columns,
        status_values=_status_values(job),
        value_mappings=tuple(ValueMapping(o.field, o.source_value, o.value) for o in mapping.values),
    )


def _preview_row(row: ParsedRow, item_id: int | None = None) -> PreviewRow:
    return PreviewRow(
        row_number=row.row_number,
        action=row.action,
        legacy_ref=row.legacy_ref,
        title=row.title,
        status=row.status,
        outcome=row.outcome,
        submitted_on=row.submitted_on,
        partner=row.partner_name,
        problem_count=len(row.problems),
        item_id=item_id,
    )


def _counts(rows: tuple[ParsedRow, ...]) -> ImportCounts:
    actions = Counter(r.action for r in rows)
    return ImportCounts(
        rows_total=len(rows),
        ready=actions[RowAction.CREATE],
        duplicates=actions[RowAction.SKIP_DUPLICATE],
        already_imported=actions[RowAction.SKIP_ALREADY_IMPORTED],
        not_data=actions[RowAction.SKIP_NOT_DATA],
        blocked=actions[RowAction.BLOCKED],
    )


def get_preview(*, viewer: User, job_id: int) -> ImportPreview:
    require_role(viewer, Role.ADMIN)
    job = _job(job_id)
    status = ImportStatus(job.status)
    sheet_problems: tuple[Problem, ...] = ()
    unmapped: tuple[UnmappedValue, ...] = ()
    item_ids: tuple[int | None, ...]
    if status is ImportStatus.COMMITTED:
        stored: list[tuple[object, int | None]] = list(
            ImportRow.objects.filter(job=job).order_by("row_number").values_list("parsed", "item")
        )
        rows = tuple(_PARSED_ROW.validate_python(parsed) for parsed, _ in stored)
        item_ids = tuple(item_id for _, item_id in stored)
        counts = _counts(rows)
    else:
        result = evaluate(job)
        rows, counts, sheet_problems, unmapped = result.rows, result.counts, result.problems, result.unmapped
        item_ids = (None,) * len(rows)
    return ImportPreview(
        job_id=job.pk,
        status=status,
        counts=counts,
        problems=sheet_problems + tuple(p for r in rows for p in r.problems),
        unmapped=unmapped,
        rows=tuple(_preview_row(r, i) for r, i in zip(rows, item_ids, strict=True)),
    )
