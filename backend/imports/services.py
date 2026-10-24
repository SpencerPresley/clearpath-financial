"""Import actions: upload, map, request commit, and the commit job itself. Admins only (spec §1, Users).

Commit runs as a Celery job (anything that can pass CloudFront's 60 s origin timeout does; ledger References).
`request_commit` enqueues it on transaction commit rather than through the outbox: "commit requested" isn't a
domain event, and the job is idempotent on its own row, so re-POSTing commit after a lost enqueue is safe.
"""

import io
import logging
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import IO, Final

from django.core.files.base import ContentFile
from django.db import connection, transaction
from pydantic import TypeAdapter

from accounts.models import User
from audit.payloads import ImportCommittedPayload, ItemImportedPayload, PartnerCreatedPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import (
    Channel,
    CheckStatus,
    DecisionOutcome,
    EntityType,
    EventType,
    ItemStatus,
    PartnerStatus,
    PartnerType,
    Product,
    RiskTier,
    Role,
)
from core.errors import Conflict, FieldIssue, InvalidInput, NotFound
from core.permissions import require_role
from imports.domain import ImportStatus, ImportTargetField, ImportValueField, RowAction
from imports.mapping import (
    IMPLIED_OUTCOME,
    IMPORTABLE_STATUSES,
    PARTNER_STATUS_MAP,
    PARTNER_TYPE_MAP,
    TARGET_LABELS,
    guess_column_mapping,
    partner_key,
    value_key,
)
from imports.models import ImportJob, ImportRow
from imports.normalize import (
    ImportMapping,
    NormalizedImport,
    ParsedRow,
    PartnerDirectory,
    StatusOverride,
    ValueOverride,
    normalize,
)
from imports.workbook import MAX_BYTES, SAMPLE_TRACKER_PATH, RawWorkbook, UnreadableWorkbookError, read_workbook
from partners.models import Partner
from reviews.models import ReviewItem

logger = logging.getLogger(__name__)

# Serializes commits across jobs, so "is this legacy_ref already imported?" can't race another commit.
_COMMIT_LOCK_KEY: Final = 0x494D504F5254  # "IMPORT"
_PARSED_ROW: Final = TypeAdapter(ParsedRow)
_TRIGGER_LABELS: Final = {True: "yes", False: "no", None: "unknown"}
_EDITABLE: Final = frozenset({ImportStatus.UPLOADED, ImportStatus.MAPPED, ImportStatus.FAILED})

# The outcome each importable status allows, when the admin names one explicitly.
_ALLOWED_OUTCOMES: Final[dict[ItemStatus, frozenset[DecisionOutcome | None]]] = {
    ItemStatus.SUBMITTED: frozenset({None}),
    ItemStatus.IN_REVIEW: frozenset({None}),
    ItemStatus.CHANGES_REQUESTED: frozenset({DecisionOutcome.CHANGES_REQUESTED}),
    ItemStatus.APPROVED: frozenset({DecisionOutcome.APPROVED, DecisionOutcome.APPROVED_WITH_EDITS}),
    ItemStatus.REJECTED: frozenset({DecisionOutcome.REJECTED}),
}


# --- shared reads of a job ------------------------------------------------------------------------------------


def job_workbook(job: ImportJob) -> RawWorkbook:
    return RawWorkbook.model_validate(job.workbook)


def job_mapping(job: ImportJob) -> ImportMapping:
    return ImportMapping(
        columns={h: ImportTargetField(t) for h, t in job.column_mapping.items()},
        statuses=tuple(
            StatusOverride(
                source_value=s["source_value"],
                status=ItemStatus(s["status"]),
                outcome=DecisionOutcome(s["outcome"]) if s.get("outcome") else None,
            )
            for s in job.status_mapping
        ),
        values=tuple(
            ValueOverride(field=ImportValueField(v["field"]), source_value=v["source_value"], value=v["value"])
            for v in job.value_mapping
        ),
    )


def partner_directory(workbook: RawWorkbook) -> PartnerDirectory:
    return PartnerDirectory.build(
        existing=Partner.objects.values_list("name", flat=True), sheet=[p.name for p in workbook.partners]
    )


def evaluate(job: ImportJob) -> NormalizedImport:
    """What commit would do right now. Two passes: the first finds the refs the sheet would create, the second
    re-runs with the ones of those that already exist, so the lookup stays proportional to the sheet."""
    workbook, mapping = job_workbook(job), job_mapping(job)
    directory = partner_directory(workbook)
    first = normalize(workbook, mapping, directory, frozenset())
    candidates = [r.legacy_ref for r in first.rows if r.legacy_ref and r.action is not RowAction.SKIP_DUPLICATE]
    existing = frozenset(
        ReviewItem.objects.filter(legacy_ref__in=candidates).values_list("legacy_ref", flat=True).iterator()
    )
    if not existing:
        return first
    return normalize(workbook, mapping, directory, frozenset(r for r in existing if r))


def _job_for_update(job_id: int) -> ImportJob:
    job = ImportJob.objects.select_for_update().filter(pk=job_id).first()
    if job is None:
        raise NotFound.entity("import", job_id)
    return job


# --- upload ---------------------------------------------------------------------------------------------------


def create_import(*, actor: User, filename: str, source: IO[bytes], clock: Clock = SYSTEM_CLOCK) -> int:
    """Read the workbook, guess the column mapping, and keep the file. Returns the job id."""
    require_role(actor, Role.ADMIN)
    data = source.read(MAX_BYTES + 1)
    try:
        workbook = read_workbook(io.BytesIO(data))
    except UnreadableWorkbookError as exc:
        raise InvalidInput.for_field("file", str(exc)) from exc
    now = clock.now()
    with transaction.atomic():
        job = ImportJob(
            filename=filename[:255],
            sheet_name=workbook.tracker.name[:100],
            row_count=len(workbook.tracker.rows),
            workbook=workbook.model_dump(mode="json"),
            column_mapping={h: t.value for h, t in guess_column_mapping(workbook.tracker.headers).items()},
            created_by=actor,
            created_at=now,
            updated_at=now,
        )
        job.file.save(f"{uuid.uuid4().hex}.xlsx", ContentFile(data), save=False)
        job.save()
    return job.pk


def create_sample_import(*, actor: User, clock: Clock = SYSTEM_CLOCK) -> int:
    """ "Load sample tracker": the bundled copy of samples/clearpath_review_tracker.xlsx."""
    with SAMPLE_TRACKER_PATH.open("rb") as source:
        return create_import(actor=actor, filename=SAMPLE_TRACKER_PATH.name, source=source, clock=clock)


# --- mapping --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MappingUpdate:
    """What the admin changed. `columns` merge into the saved mapping; a list left as None keeps the saved one,
    so a PUT that only remaps a column doesn't erase status or value mappings."""

    columns: Mapping[str, ImportTargetField] = field(default_factory=dict)
    statuses: tuple[StatusOverride, ...] | None = None
    values: tuple[ValueOverride, ...] | None = None


def _invalid(loc: tuple[str | int, ...], message: str) -> InvalidInput:
    return InvalidInput(message, fields=[FieldIssue(loc=("body", *loc), message=message)])


def _check_status_override(o: StatusOverride, index: int) -> StatusOverride:
    if o.status not in IMPORTABLE_STATUSES:
        raise _invalid(("status_values", index, "status"), f"Imported items can't be {o.status.replace('_', ' ')}.")
    outcome = o.outcome or IMPLIED_OUTCOME.get(o.status)
    if outcome not in _ALLOWED_OUTCOMES[o.status]:
        message = f"A {o.status.replace('_', ' ')} item can't have that decision."
        raise _invalid(("status_values", index, "outcome"), message)
    return StatusOverride(source_value=o.source_value, status=o.status, outcome=outcome)


def _check_value_override(o: ValueOverride, index: int, directory: PartnerDirectory) -> ValueOverride:
    valid: Iterable[str]
    match o.field:
        case ImportValueField.PRODUCT:
            valid = [p.value for p in Product]
        case ImportValueField.CHANNEL:
            valid = [c.value for c in Channel]
        case ImportValueField.RISK_TIER:
            valid = [r.value for r in RiskTier]
        case ImportValueField.TRIGGER_TERMS:
            valid = ["yes", "no"]
        case ImportValueField.PARTNER:
            valid = directory.names.values()
    if o.value not in valid:
        label = TARGET_LABELS[ImportTargetField(o.field)]
        raise _invalid(("value_mappings", index, "value"), f"{o.value!r} isn't a valid {label}.")
    return o


def _check_columns(
    headers: Sequence[str], saved: Mapping[str, str], update: Mapping[str, ImportTargetField]
) -> dict[str, str]:
    for i, header in enumerate(update):
        if header not in headers:
            raise _invalid(("columns", i, "source"), f"The sheet has no column {header!r}.")
    merged = {**saved, **{h: t.value for h, t in update.items()}}
    claimed: dict[str, str] = {}
    for header in headers:
        target = merged.get(header, ImportTargetField.IGNORE.value)
        if target == ImportTargetField.IGNORE.value:
            continue
        if target in claimed:
            label = TARGET_LABELS[ImportTargetField(target)]
            raise _invalid(
                ("columns",), f"{label} is mapped from both {claimed[target]!r} and {header!r}; set one to Ignore."
            )
        claimed[target] = header
    return merged


def set_mapping(*, actor: User, job_id: int, update: MappingUpdate, clock: Clock = SYSTEM_CLOCK) -> None:
    """Save the admin's column, status-value, and value mappings."""
    require_role(actor, Role.ADMIN)
    with transaction.atomic():
        job = _job_for_update(job_id)
        if ImportStatus(job.status) not in _EDITABLE:
            raise Conflict(f"This import is {job.status}; its mapping can't change.")
        workbook = job_workbook(job)
        job.column_mapping = _check_columns(workbook.tracker.headers, job.column_mapping, update.columns)
        if update.statuses is not None:
            job.status_mapping = [
                {
                    "source_value": o.source_value,
                    "status": o.status.value,
                    "outcome": o.outcome.value if o.outcome else None,
                }
                for o in (_check_status_override(o, i) for i, o in enumerate(update.statuses))
            ]
        if update.values is not None:
            directory = partner_directory(workbook)
            job.value_mapping = [
                {"field": o.field.value, "source_value": o.source_value, "value": o.value}
                for o in (_check_value_override(o, i, directory) for i, o in enumerate(update.values))
            ]
        job.status = ImportStatus.MAPPED.value
        job.error = ""
        job.updated_at = clock.now()
        job.save()


# --- commit ---------------------------------------------------------------------------------------------------


def _blocked_message(n: int) -> str:
    return f"{n} {'row has' if n == 1 else 'rows have'} problems. Fix the mapping or skip them."


def _enqueue_commit(job_id: int) -> None:
    from imports.tasks import commit_import_task  # noqa: PLC0415  # tasks imports this module

    commit_import_task.delay(job_id)


def request_commit(*, actor: User, job_id: int, skip_blocked: bool = True, clock: Clock = SYSTEM_CLOCK) -> None:
    """Queue the commit job. Idempotent: a committed job is left alone, and a job already committing is
    re-enqueued (the job itself no-ops if another run got there first)."""
    require_role(actor, Role.ADMIN)
    with transaction.atomic():
        job = _job_for_update(job_id)
        status = ImportStatus(job.status)
        if status is ImportStatus.COMMITTED:
            return
        if status is not ImportStatus.COMMITTING:
            result = evaluate(job)
            if result.problems:
                raise Conflict(result.problems[0].message)
            if result.counts.blocked and not skip_blocked:
                raise Conflict(_blocked_message(result.counts.blocked))
            job.status = ImportStatus.COMMITTING.value
            job.skip_blocked_rows = skip_blocked
            job.commit_requested_by = actor
            job.commit_requested_at = clock.now()
            job.error = ""
            job.updated_at = clock.now()
            job.save()
        transaction.on_commit(lambda: _enqueue_commit(job_id))


def _midnight(on: date | None) -> datetime | None:
    return datetime(on.year, on.month, on.day, tzinfo=UTC) if on else None


def _notes(row: ParsedRow, *, sheet: str, trigger_mapped: bool) -> str:
    lines = [f"Imported from {sheet} row {row.row_number}."]
    if row.approver:
        lines.append(f"Approved by {row.approver}{' (date from the last round)' if row.approval_derived else ''}.")
    if trigger_mapped:
        lines.append(f"Trigger terms: {_TRIGGER_LABELS[row.trigger_terms]}.")
    if row.version_number is not None:
        lines.append(f"Tracker version: v{row.version_number}.")
    if row.placement:
        lines.append(f"Placement: {row.placement}")
    if row.notes:
        lines.append(row.notes)
    return "\n".join(lines)


@dataclass(frozen=True)
class _PartnerIds:
    by_key: dict[str, int]

    def get(self, name: str | None) -> int | None:
        return self.by_key.get(partner_key(name)) if name else None


def _ensure_partners(workbook: RawWorkbook, *, actor: User | None, at: datetime) -> tuple[_PartnerIds, int]:
    """Create every Partners-sheet partner the app doesn't have, with an event each. "Doesn't have" uses the key
    rows resolve with (`partner_key`), so an app "Lend Compare" isn't duplicated by a sheet "LendCompare".
    Not via `partners.services.create_partner`: that action is the Lead's, and an import runs as an admin."""
    existing = {partner_key(name): pk for pk, name in Partner.objects.values_list("pk", "name")}
    created = 0
    for row in workbook.partners:
        if partner_key(row.name) in existing:
            continue
        type_ = PARTNER_TYPE_MAP.get(value_key(row.type or ""), PartnerType.AFFILIATE)
        status = PARTNER_STATUS_MAP.get(value_key(row.status or ""), PartnerStatus.ACTIVE)
        notes = "\n".join(t for t in (row.description, row.notes) if t)
        partner = Partner.objects.create(
            name=row.name[:200],
            type=type_.value,
            status=status.value,
            contact_email=(row.contact_email or "")[:254],
            agreement_signed_on=row.agreement_date,
            notes=notes,
            created_at=at,
            updated_at=at,
        )
        record_event(
            type=EventType.PARTNER_CREATED,
            entity=EntityType.PARTNER,
            entity_id=partner.pk,
            payload=PartnerCreatedPayload(partner_id=partner.pk, name=partner.name, type=type_),
            actor=actor,
            at=at,
        )
        existing[partner_key(row.name)] = partner.pk
        created += 1
    return _PartnerIds(existing), created


def _create_item(row: ParsedRow, *, partner_id: int | None, notes: str, at: datetime) -> ReviewItem:
    submitted_at = _midnight(row.submitted_on)
    # normalize blocks any row missing one of these, so a CREATE row always has them.
    status, product, channel, risk_tier, title = row.status, row.product, row.channel, row.risk_tier, row.title
    if not (status and product and channel and risk_tier and title and row.legacy_ref and submitted_at):
        raise ValueError(f"row {row.row_number} isn't complete enough to create an item")
    approved = status is ItemStatus.APPROVED
    return ReviewItem.objects.create(
        title=title,
        product=product.value,
        channel=channel.value,
        partner_id=partner_id,
        markets=[],
        status=status.value,
        round=row.rounds or 1,
        risk_tier=risk_tier.value,
        llm_check_status=CheckStatus.SKIPPED.value,
        is_legacy=True,
        legacy_ref=row.legacy_ref,
        legacy_submitter=(row.submitter or "")[:200],
        legacy_reviewer=(row.reviewer or "")[:200],
        legacy_history=row.comments or "",
        notes=notes,
        source_url=row.asset_url or "",
        submitted_at=submitted_at,
        queue_entered_at=submitted_at,  # the tracker records no later re-entry
        approved_at=_midnight(row.approved_on) if approved else None,
        approval_expires_at=_midnight(row.expires_on) if approved else None,
        created_at=at,
        updated_at=at,
    )


def commit_import(*, job_id: int, clock: Clock = SYSTEM_CLOCK) -> None:
    """The commit job: create the legacy items, their partners, and one ITEM_IMPORTED event per item, in one
    transaction. Re-running a committed job does nothing; refs already in the app are skipped."""
    now = clock.now()
    with transaction.atomic():
        job = _job_for_update(job_id)
        if job.status != ImportStatus.COMMITTING.value:
            logger.info("import commit skipped job_id=%d status=%s", job_id, job.status)
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_COMMIT_LOCK_KEY])
        actor = job.commit_requested_by
        result = evaluate(job)
        if result.problems:
            raise Conflict(result.problems[0].message)
        if result.counts.blocked and not job.skip_blocked_rows:
            raise Conflict(_blocked_message(result.counts.blocked))

        workbook = job_workbook(job)
        partners, partners_created = _ensure_partners(workbook, actor=actor, at=now)
        trigger_mapped = ImportTargetField.TRIGGER_TERMS.value in job.column_mapping.values()
        records: list[ImportRow] = []
        created = 0
        for row in result.rows:
            item = None
            if row.action is RowAction.CREATE:
                notes = _notes(row, sheet=job.sheet_name, trigger_mapped=trigger_mapped)
                item = _create_item(row, partner_id=partners.get(row.partner_name), notes=notes, at=now)
                record_event(
                    type=EventType.ITEM_IMPORTED,
                    entity=EntityType.ITEM,
                    entity_id=item.pk,
                    item_id=item.pk,
                    payload=ItemImportedPayload(
                        import_id=job.pk,
                        legacy_ref=item.legacy_ref or "",
                        row_number=row.row_number,
                        timeline=row.timeline,  # pyrefly: ignore[bad-argument-type]  # set on every CREATE row
                    ),
                    actor=actor,
                    at=now,
                    to_status=row.status,
                )
                created += 1
            records.append(
                ImportRow(
                    job=job,
                    row_number=row.row_number,
                    legacy_ref=row.legacy_ref,
                    action=row.action.value,
                    item=item,
                    parsed=_PARSED_ROW.dump_python(row, mode="json"),
                )
            )
        ImportRow.objects.bulk_create(records)

        job.status = ImportStatus.COMMITTED.value
        job.committed_at = now
        job.created_count = created
        job.skipped_count = len(result.rows) - created
        job.partners_created_count = partners_created
        job.updated_at = now
        job.save()
        record_event(
            type=EventType.IMPORT_COMMITTED,
            entity=EntityType.IMPORT,
            entity_id=job.pk,
            payload=ImportCommittedPayload(import_id=job.pk, created_count=created, skipped_count=job.skipped_count),
            actor=actor,
            at=now,
        )
    logger.info("import committed job_id=%d created=%d skipped=%d", job_id, created, job.skipped_count)


def mark_import_failed(*, job_id: int, error: str, clock: Clock = SYSTEM_CLOCK) -> None:
    """Record a failed commit after its transaction rolled back. The admin can fix and commit again."""
    with transaction.atomic():
        job = _job_for_update(job_id)
        if job.status == ImportStatus.COMMITTED.value:
            return
        job.status = ImportStatus.FAILED.value
        job.error = error[:500]
        job.updated_at = clock.now()
        job.save()
