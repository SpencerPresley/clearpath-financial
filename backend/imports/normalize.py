"""Tracker rows -> typed legacy-item drafts plus the problems an admin should see. Pure: no Django, no I/O.

Preview and commit both call `normalize`, so what the admin previewed is what gets committed (commit re-runs it
with the refs that exist at that moment). Every rule here is specified in samples/README.md; where it says
"Importer should", the tests in `tests/test_normalize.py` read that table and check this module against it.
"""

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Final

from pydantic import ValidationError

from audit.payloads import LegacyTimeline
from core.domain import Channel, DecisionOutcome, ItemStatus, Product, RiskTier
from imports.domain import ImportProblemKind, ImportTargetField, ImportValueField, ProblemSeverity, RowAction
from imports.mapping import (
    CHANNEL_MAP,
    DEFAULT_STATUS_MAP,
    PRODUCT_MAP,
    REQUIRED_TARGETS,
    RISK_TIER_MAP,
    TARGET_LABELS,
    TRIGGER_TERMS_MAP,
    TRIGGER_UNKNOWN,
    StatusTarget,
    partner_key,
    value_key,
)
from imports.workbook import EMPTY, RawCell, RawRow, RawWorkbook
from reviews.risk import derive_risk_tier

T = ImportTargetField
K = ImportProblemKind
S = ProblemSeverity

TITLE_MAX: Final = 300
REF_MAX: Final = 64
URL_MAX: Final = 2000

# A data row's Request ID: no spaces, at least one digit (MCR-26-045, 1042). Column A of the merged note row
# ("NOTE (R. Okafor 1/5/26): ...") fails it, which is how non-data rows are recognized.
_REF = re.compile(r"^(?=.*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
_REF_YEAR = re.compile(r"^[A-Za-z]+-(\d{2})-")
# samples/README.md "Comment grammar". Split on the match starts; segment text never contains the pattern.
_SEGMENT = re.compile(r"R(?P<round>\d+) (?P<month>\d{1,2})/(?P<day>\d{1,2}) (?P<initials>[A-Z]{2}):")
_US_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_MONTH_DAY = re.compile(r"^([A-Za-z]{3})[a-z]*\.? (\d{1,2})$")
_MONTHS: Final = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_APPROVAL = re.compile(r"^(?P<date>\d{1,2}/\d{1,2}/(?:\d{2}|\d{4}))(?:\s*-\s*(?P<who>.+))?$")
_INITIAL_LAST = re.compile(r"^(?P<initial>[A-Za-z])\.?\s+(?P<last>.+)$")
_URL = re.compile(r"https?://[^\s;,]+")
_TRAILING_SEPARATOR = re.compile(r"[\s\-:;|]+$")
_SUFFIXES: Final = "bcdefghijklmnopqrstuvwxyz"


# --- inputs ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusOverride:
    source_value: str
    status: ItemStatus
    outcome: DecisionOutcome | None


@dataclass(frozen=True)
class ValueOverride:
    field: ImportValueField
    source_value: str
    value: str  # an enum value, a partner name, or "yes" / "no" / "unknown" for trigger terms


@dataclass(frozen=True)
class ImportMapping:
    columns: Mapping[str, ImportTargetField]  # header -> target
    statuses: tuple[StatusOverride, ...] = ()
    values: tuple[ValueOverride, ...] = ()


@dataclass(frozen=True)
class PartnerMatch:
    name: str
    fuzzy: bool


@dataclass(frozen=True)
class PartnerDirectory:
    """Canonical partner names, keyed by `partner_key`. App partners win over sheet spellings."""

    names: Mapping[str, str]

    @classmethod
    def build(cls, *, existing: Iterable[str], sheet: Iterable[str]) -> "PartnerDirectory":
        names = {partner_key(n): n for n in sheet}
        names.update({partner_key(n): n for n in existing})
        return cls(names=names)

    def resolve(self, raw: str) -> PartnerMatch | None:
        """Normalized key, then a unique prefix (`CardPerks` -> `CardPerks Weekly`)."""
        key = partner_key(raw)
        if not key:
            return None
        name = self.names.get(key)
        if name is None:
            prefixed = [n for k, n in self.names.items() if k.startswith(key)]
            if len(prefixed) != 1:
                return None
            name = prefixed[0]
        return PartnerMatch(name=name, fuzzy=name != raw)


# --- outputs ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Problem:
    row_number: int | None  # None: about the whole sheet (a missing column mapping)
    column: str | None  # the sheet's header text
    kind: ImportProblemKind
    severity: ProblemSeverity
    value: str | None
    message: str


@dataclass(frozen=True)
class CommentSegment:
    round: int
    on: date
    initials: str
    text: str


@dataclass(frozen=True)
class UnmappedValue:
    field: ImportTargetField
    value: str
    rows: int


@dataclass(frozen=True)
class ParsedRow:
    row_number: int
    action: RowAction
    source_ref: str | None  # the Request ID as typed (stripped)
    legacy_ref: str | None  # unique in the app: source_ref, or source_ref-b for a reused ID
    title: str | None = None
    asset_url: str | None = None
    submitter: str | None = None
    product: Product | None = None
    channel: Channel | None = None
    partner_name: str | None = None
    risk_tier: RiskTier | None = None
    trigger_terms: bool | None = None
    reviewer: str | None = None
    version_number: int | None = None
    rounds: int | None = None
    status: ItemStatus | None = None
    outcome: DecisionOutcome | None = None
    submitted_on: date | None = None
    approver: str | None = None
    approved_on: date | None = None
    approval_derived: bool = False
    expires_on: date | None = None
    comments: str | None = None
    segments: tuple[CommentSegment, ...] = ()
    placement: str | None = None
    placement_urls: tuple[str, ...] = ()
    notes: str | None = None
    timeline: LegacyTimeline | None = None
    problems: tuple[Problem, ...] = ()
    duplicate_of: int | None = None  # the row this one repeats


@dataclass(frozen=True)
class ImportCounts:
    rows_total: int
    ready: int
    duplicates: int
    already_imported: int
    not_data: int
    blocked: int


@dataclass(frozen=True)
class NormalizedImport:
    rows: tuple[ParsedRow, ...]
    problems: tuple[Problem, ...]  # sheet-level (missing mappings)
    unmapped: tuple[UnmappedValue, ...]
    counts: ImportCounts

    @property
    def all_problems(self) -> tuple[Problem, ...]:
        return self.problems + tuple(p for r in self.rows for p in r.problems)


# --- cell parsing ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedDate:
    on: date | None
    coerced: bool  # read from text rather than an Excel date
    failed: bool


def ref_year(ref: str) -> int | None:
    m = _REF_YEAR.match(ref)
    return 2000 + int(m.group(1)) if m else None


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(cell: RawCell, *, year_hint: int | None) -> ParsedDate:
    """Real dates, `M/D/YY` (US order, 20YY), `M/D/YYYY`, ISO `YYYY-MM-DD`, and `Mon D` with the year from
    `year_hint` (the Request ID's `MCR-YY-` prefix)."""
    if cell.when is not None:
        return ParsedDate(cell.when.date(), coerced=False, failed=False)
    text = cell.text
    if text is None:
        return ParsedDate(None, coerced=False, failed=cell.number is not None)
    on: date | None = None
    if m := _US_DATE.match(text):
        year = int(m.group(3))
        on = _date(year + 2000 if year < 100 else year, int(m.group(1)), int(m.group(2)))  # noqa: PLR2004
    elif m := _ISO_DATE.match(text):
        on = _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    elif (m := _MONTH_DAY.match(text)) and year_hint is not None and m.group(1).casefold() in _MONTHS:
        on = _date(year_hint, _MONTHS.index(m.group(1).casefold()) + 1, int(m.group(2)))
    return ParsedDate(on, coerced=on is not None, failed=on is None)


def parse_segments(comments: str, *, submitted_on: date) -> tuple[tuple[CommentSegment, ...], bool]:
    """Split the comments cell into rounds. Segment dates have no year: start from the submission year and
    add one each time the month goes backwards. Returns (segments, every date was valid)."""
    matches = list(_SEGMENT.finditer(comments))
    year, prev_month = submitted_on.year, submitted_on.month
    out: list[CommentSegment] = []
    valid = True
    for i, m in enumerate(matches):
        month, day = int(m.group("month")), int(m.group("day"))
        if month < prev_month:
            year += 1
        prev_month = month
        end = matches[i + 1].start() if i + 1 < len(matches) else len(comments)
        on = _date(year, month, day)
        if on is None:
            valid = False
            continue
        out.append(
            CommentSegment(
                round=int(m.group("round")), on=on, initials=m.group("initials"), text=comments[m.end() : end].strip()
            )
        )
    return tuple(out), valid


def resolve_person(raw: str, people: Sequence[str]) -> str | None:
    """`L. Brandt` or `Leah Brandt` -> the full name in `people`, if exactly one matches."""
    folded = raw.casefold()
    exact = [p for p in people if p.casefold() == folded]
    if exact:
        return exact[0]
    m = _INITIAL_LAST.match(raw)
    if not m:
        return None
    initial, last = m.group("initial").casefold(), m.group("last").casefold()
    hits = {
        p
        for p in people
        if (parts := p.split())
        and len(parts) > 1
        and parts[0][0].casefold() == initial
        and parts[-1].casefold() == last
    }
    return hits.pop() if len(hits) == 1 else None


def split_asset(cell: RawCell) -> tuple[str | None, str | None]:
    """(title, url) from the three shapes: a hyperlinked file name, `<name> - <url>` text, or a bare name."""
    text = cell.text
    if cell.hyperlink:
        return (text or cell.hyperlink)[:TITLE_MAX], cell.hyperlink
    if text is None:
        return None, None
    m = _URL.search(text)
    if m is None:
        return text[:TITLE_MAX], None
    title = _TRAILING_SEPARATOR.sub("", text[: m.start()]).strip()
    url = m.group(0)
    return (title or url.rsplit("/", 1)[-1] or url)[:TITLE_MAX], url


def _int(cell: RawCell) -> int | None:
    if cell.number is not None and cell.number.is_integer() and cell.number >= 1:
        return int(cell.number)
    if cell.text is not None and cell.text.isdigit() and int(cell.text) >= 1:
        return int(cell.text)
    return None


# --- one row ---------------------------------------------------------------------------------------------------


@dataclass
class _RowParser:
    """Parses one data row; collects problems instead of raising."""

    row: RawRow
    columns: Mapping[ImportTargetField, int]
    headers: Sequence[str]
    statuses: Mapping[str, StatusTarget]
    values: Mapping[tuple[ImportValueField, str], str]
    directory: PartnerDirectory
    reviewers: Sequence[str]
    problems: list[Problem] = field(default_factory=list)
    unmapped: list[tuple[ImportTargetField, str]] = field(default_factory=list)

    def cell(self, target: ImportTargetField) -> RawCell:
        i = self.columns.get(target)
        return self.row.cells[i] if i is not None else EMPTY

    def mapped(self, target: ImportTargetField) -> bool:
        return target in self.columns

    def problem(
        self, target: ImportTargetField | None, kind: ImportProblemKind, severity: ProblemSeverity, message: str
    ) -> None:
        i = self.columns.get(target) if target is not None else None
        value = self.row.cells[i].display if i is not None else None
        column = self.headers[i] if i is not None else None
        self.problems.append(Problem(self.row.row_number, column, kind, severity, value, message))

    def override(self, field_: ImportValueField, raw: str) -> str | None:
        return self.values.get((field_, value_key(raw)))

    def enum_value[E: Product | Channel | RiskTier](
        self, target: ImportTargetField, table: Mapping[str, E], enum: type[E], *, required: bool
    ) -> E | None:
        raw = self.cell(target).display
        label = TARGET_LABELS[target]
        if raw is None:
            if required:
                self.problem(target, K.MISSING_VALUE, S.ERROR, f"{label} is blank.")
            return None
        mapped = self.override(ImportValueField(target.value), raw)
        if mapped is not None:
            return enum(mapped)
        hit = table.get(value_key(raw))
        if hit is None:
            self.unmapped.append((target, raw))
            severity = S.ERROR if required else S.WARNING
            self.problem(target, K.UNKNOWN_VALUE, severity, f"{label} {raw!r} isn't a known value; map it.")
        return hit

    def parse(self, ref: str) -> ParsedRow:  # noqa: C901, PLR0912, PLR0915  # one block per tracker column
        year_hint = ref_year(ref)

        submitted = parse_date(self.cell(T.SUBMITTED_ON), year_hint=year_hint)
        if submitted.on is None:
            if submitted.failed:
                self.problem(T.SUBMITTED_ON, K.UNPARSEABLE_DATE, S.ERROR, "Date submitted isn't a date.")
            else:
                self.problem(T.SUBMITTED_ON, K.MISSING_VALUE, S.ERROR, "Date submitted is blank.")
        elif submitted.coerced:
            self.problem(T.SUBMITTED_ON, K.COERCED_DATE, S.INFO, f"Read as {submitted.on.isoformat()}.")

        title, asset_url = split_asset(self.cell(T.TITLE))
        if title is None:
            self.problem(T.TITLE, K.MISSING_VALUE, S.ERROR, "Title is blank.")
        if asset_url is not None and len(asset_url) > URL_MAX:
            asset_url = None

        product = self.enum_value(T.PRODUCT, PRODUCT_MAP, Product, required=True)
        channel = self.enum_value(T.CHANNEL, CHANNEL_MAP, Channel, required=True)

        partner_name: str | None = None
        partner_raw = self.cell(T.PARTNER).display
        if partner_raw is not None:
            mapped_partner = self.override(ImportValueField.PARTNER, partner_raw)
            match = PartnerMatch(mapped_partner, fuzzy=False) if mapped_partner else self.directory.resolve(partner_raw)
            if match is None:
                self.unmapped.append((T.PARTNER, partner_raw))
                self.problem(T.PARTNER, K.UNKNOWN_PARTNER, S.ERROR, f"No partner matches {partner_raw!r}; map it.")
            else:
                partner_name = match.name
                if match.fuzzy:
                    self.problem(T.PARTNER, K.FUZZY_PARTNER, S.WARNING, f"Matched to partner {match.name!r}.")

        risk_tier: RiskTier | None = None
        if self.mapped(T.RISK_TIER):
            risk_tier = self.enum_value(T.RISK_TIER, RISK_TIER_MAP, RiskTier, required=False)
        if risk_tier is None and product is not None and channel is not None:
            risk_tier = derive_risk_tier(
                product=product, channel=channel, has_partner=partner_name is not None, is_prescreen=False
            )

        trigger_terms = self.trigger_terms()

        segments: tuple[CommentSegment, ...] = ()
        comments = self.cell(T.COMMENTS).text
        if comments and submitted.on is not None:
            segments, valid = parse_segments(comments, submitted_on=submitted.on)
            if not valid:
                self.problem(T.COMMENTS, K.UNPARSEABLE_DATE, S.WARNING, "A round's date isn't a real date; skipped it.")

        rounds = _int(self.cell(T.ROUNDS)) or max(len(segments), 1)
        version_number = _int(self.cell(T.VERSION_NUMBER))

        status_target = self.status()
        approval = self.cell(T.APPROVAL)
        approver_raw: str | None = None
        approved_on: date | None = None
        if approval.when is not None:
            approved_on = approval.when.date()
        elif approval.text is not None:
            if m := _APPROVAL.match(approval.text):
                approved_on = parse_date(RawCell(text=m.group("date")), year_hint=None).on
                approver_raw = m.group("who")
            else:
                approver_raw = approval.text
        approver = None
        if approver_raw is not None:
            approver = resolve_person(approver_raw, self.reviewers)
            if approver is None:
                approver = approver_raw
                self.problem(T.APPROVAL, K.UNRESOLVED_APPROVER, S.WARNING, f"No reviewer matches {approver_raw!r}.")

        approval_derived = False
        is_approved = status_target is not None and status_target.status is ItemStatus.APPROVED
        if is_approved and approved_on is None and segments:
            approved_on = segments[-1].on
            approval_derived = True
            self.problem(
                T.APPROVAL,
                K.DERIVED_APPROVAL_DATE,
                S.WARNING,
                f"Approval date taken from the last round: {approved_on.isoformat()}.",
            )

        expires = parse_date(self.cell(T.EXPIRES_ON), year_hint=year_hint)
        if expires.failed:
            self.problem(T.EXPIRES_ON, K.UNPARSEABLE_DATE, S.WARNING, "Approval expiry isn't a date; left blank.")
        elif expires.coerced and expires.on is not None:
            self.problem(T.EXPIRES_ON, K.COERCED_DATE, S.INFO, f"Read as {expires.on.isoformat()}.")
        elif is_approved and expires.on is None:
            self.problem(T.EXPIRES_ON, K.MISSING_EXPIRY, S.WARNING, "Approved with no expiry; left blank.")

        placement_cell = self.cell(T.PLACEMENT)
        urls = ([placement_cell.hyperlink] if placement_cell.hyperlink else []) + _URL.findall(
            placement_cell.text or ""
        )
        placement_urls = tuple(dict.fromkeys(urls))

        timeline = None
        if submitted.on is not None and status_target is not None:
            timeline = self.timeline(submitted.on, segments, status_target, approved_on, rounds)

        return ParsedRow(
            row_number=self.row.row_number,
            action=RowAction.CREATE,
            source_ref=ref,
            legacy_ref=ref,
            title=title,
            asset_url=asset_url,
            submitter=self.cell(T.SUBMITTER).display,
            product=product,
            channel=channel,
            partner_name=partner_name,
            risk_tier=risk_tier,
            trigger_terms=trigger_terms,
            reviewer=self.cell(T.REVIEWER).display,
            version_number=version_number,
            rounds=rounds,
            status=status_target.status if status_target else None,
            outcome=status_target.outcome if status_target else None,
            submitted_on=submitted.on,
            approver=approver,
            approved_on=approved_on if is_approved else None,
            approval_derived=approval_derived,
            expires_on=expires.on,
            comments=comments,
            segments=segments,
            placement=placement_cell.display,
            placement_urls=placement_urls,
            notes=self.cell(T.NOTES).display,
            timeline=timeline,
            problems=tuple(self.problems),
        )

    def trigger_terms(self) -> bool | None:
        if not self.mapped(T.TRIGGER_TERMS):
            return None
        raw = self.cell(T.TRIGGER_TERMS).display
        if raw is None or raw in TRIGGER_UNKNOWN:
            self.problem(T.TRIGGER_TERMS, K.UNKNOWN_TRIGGER_TERMS, S.WARNING, "Trigger terms unknown; left blank.")
            return None
        mapped = self.override(ImportValueField.TRIGGER_TERMS, raw)
        if mapped is not None:
            return TRIGGER_TERMS_MAP.get(mapped)
        hit = TRIGGER_TERMS_MAP.get(value_key(raw))
        if hit is None:
            self.unmapped.append((T.TRIGGER_TERMS, raw))
            self.problem(T.TRIGGER_TERMS, K.UNKNOWN_VALUE, S.WARNING, f"Trigger terms {raw!r} isn't Y or N; map it.")
        return hit

    def status(self) -> StatusTarget | None:
        raw = self.cell(T.STATUS).display
        if raw is None:
            if not self.cell(T.APPROVAL).is_empty:
                self.problem(
                    T.STATUS, K.INFERRED_STATUS, S.WARNING, "Status is blank; read as approved from the approval cell."
                )
                return StatusTarget(ItemStatus.APPROVED, DecisionOutcome.APPROVED)
            self.problem(T.STATUS, K.INFERRED_STATUS, S.INFO, "Status is blank; read as submitted.")
            return StatusTarget(ItemStatus.SUBMITTED, None)
        hit = self.statuses.get(value_key(raw))
        if hit is None:
            self.unmapped.append((T.STATUS, raw))
            self.problem(T.STATUS, K.UNMAPPED_STATUS, S.ERROR, f"Status {raw!r} isn't mapped; map it to a status.")
        return hit

    def timeline(
        self,
        submitted_on: date,
        segments: Sequence[CommentSegment],
        status: StatusTarget,
        approved_on: date | None,
        rounds: int,
    ) -> LegacyTimeline | None:
        decided_on: date | None = None
        outcome: DecisionOutcome | None = None
        if status.status in {ItemStatus.APPROVED, ItemStatus.REJECTED, ItemStatus.CHANGES_REQUESTED}:
            outcome = status.outcome
            decided_on = approved_on if status.status is ItemStatus.APPROVED and approved_on else None
            if decided_on is None and segments:
                decided_on = segments[-1].on
        try:
            return LegacyTimeline(
                submitted_at=_midnight(submitted_on),
                first_reviewed_at=_midnight(segments[0].on) if segments else None,
                decided_at=_midnight(decided_on) if decided_on else None,
                outcome=outcome,
                rounds=rounds,
            )
        except ValidationError:
            self.problem(
                T.COMMENTS,
                K.INCONSISTENT_DATES,
                S.ERROR,
                "Review dates come before the submission date; fix the dates in the sheet.",
            )
            return None


def _midnight(on: date) -> datetime:
    return datetime(on.year, on.month, on.day, tzinfo=UTC)


# --- the sheet -------------------------------------------------------------------------------------------------


def _column_index(mapping: ImportMapping, headers: Sequence[str]) -> dict[ImportTargetField, int]:
    out: dict[ImportTargetField, int] = {}
    for i, header in enumerate(headers):
        target = mapping.columns.get(header, T.IGNORE)
        if target is not T.IGNORE and target not in out:
            out[target] = i
    return out


def _status_table(overrides: Iterable[StatusOverride]) -> dict[str, StatusTarget]:
    table = dict(DEFAULT_STATUS_MAP)
    table.update({value_key(o.source_value): StatusTarget(o.status, o.outcome) for o in overrides})
    return table


def _empty(rows_total: int, problems: tuple[Problem, ...]) -> NormalizedImport:
    counts = ImportCounts(rows_total=rows_total, ready=0, duplicates=0, already_imported=0, not_data=0, blocked=0)
    return NormalizedImport(rows=(), problems=problems, unmapped=(), counts=counts)


def _not_data(row: RawRow, ref_header: str, value: str | None) -> ParsedRow:
    problem = Problem(
        row.row_number,
        ref_header,
        K.NOT_DATA_ROW,
        S.WARNING,
        value,
        "Not a data row (no Request ID); skipped.",
    )
    return ParsedRow(
        row_number=row.row_number, action=RowAction.SKIP_NOT_DATA, source_ref=None, legacy_ref=None, problems=(problem,)
    )


def normalize(
    workbook: RawWorkbook, mapping: ImportMapping, directory: PartnerDirectory, existing_refs: frozenset[str]
) -> NormalizedImport:
    sheet = workbook.tracker
    columns = _column_index(mapping, sheet.headers)
    missing = [t for t in REQUIRED_TARGETS if t not in columns]
    if missing:
        problems = tuple(
            Problem(None, None, K.MISSING_MAPPING, S.ERROR, None, f"Map a column to {TARGET_LABELS[t]}.")
            for t in missing
        )
        return _empty(len(sheet.rows), problems)

    statuses = _status_table(mapping.statuses)
    values = {(o.field, value_key(o.source_value)): o.value for o in mapping.values}
    ref_i = columns[T.LEGACY_REF]
    unmapped: Counter[tuple[ImportTargetField, str]] = Counter()

    parsed: list[ParsedRow] = []
    first_seen: dict[str, list[tuple[RawRow, ParsedRow]]] = {}
    for row in sheet.rows:
        ref_cell = row.cells[ref_i]
        ref = ref_cell.display
        if ref is None or len(ref) > REF_MAX or not _REF.match(ref):
            parsed.append(_not_data(row, sheet.headers[ref_i], ref))
            continue
        parser = _RowParser(
            row=row,
            columns=columns,
            headers=sheet.headers,
            statuses=statuses,
            values=values,
            directory=directory,
            reviewers=workbook.reviewers,
        )
        result = parser.parse(ref)
        unmapped.update(parser.unmapped)

        earlier = first_seen.setdefault(ref, [])
        twin = next(
            (
                p
                for r, p in earlier
                if r.cells == row.cells or (p.title, p.submitted_on) == (result.title, result.submitted_on)
            ),
            None,
        )
        if twin is not None:
            note = Problem(
                row.row_number,
                sheet.headers[ref_i],
                K.DUPLICATE_ROW,
                S.WARNING,
                ref,
                f"Same item as row {twin.row_number}; skipped.",
            )
            result = replace(
                result,
                action=RowAction.SKIP_DUPLICATE,
                legacy_ref=twin.legacy_ref,
                duplicate_of=twin.row_number,
                problems=(note,),
            )
        else:
            if earlier:
                suffix = _SUFFIXES[min(len(earlier), len(_SUFFIXES)) - 1]
                legacy_ref = f"{ref}-{suffix}"
                note = Problem(
                    row.row_number,
                    sheet.headers[ref_i],
                    K.REUSED_REF,
                    S.WARNING,
                    ref,
                    f"Request ID also used by row {earlier[0][0].row_number} for a different asset; "
                    f"imported as {legacy_ref}.",
                )
                result = replace(result, legacy_ref=legacy_ref, problems=(*result.problems, note))
            earlier.append((row, result))
            result = replace(result, action=_action(result, existing_refs))
            if result.action is RowAction.SKIP_ALREADY_IMPORTED:
                note = Problem(
                    row.row_number,
                    sheet.headers[ref_i],
                    K.ALREADY_IMPORTED,
                    S.WARNING,
                    result.legacy_ref,
                    f"{result.legacy_ref} is already imported; skipped.",
                )
                result = replace(result, problems=(*result.problems, note))
        parsed.append(result)

    actions = Counter(r.action for r in parsed)
    counts = ImportCounts(
        rows_total=len(sheet.rows),
        ready=actions[RowAction.CREATE],
        duplicates=actions[RowAction.SKIP_DUPLICATE],
        already_imported=actions[RowAction.SKIP_ALREADY_IMPORTED],
        not_data=actions[RowAction.SKIP_NOT_DATA],
        blocked=actions[RowAction.BLOCKED],
    )
    return NormalizedImport(
        rows=tuple(parsed),
        problems=(),
        unmapped=tuple(UnmappedValue(f, v, n) for (f, v), n in sorted(unmapped.items())),
        counts=counts,
    )


def _action(row: ParsedRow, existing_refs: frozenset[str]) -> RowAction:
    if row.legacy_ref in existing_refs:
        return RowAction.SKIP_ALREADY_IMPORTED
    if any(p.severity is S.ERROR for p in row.problems):
        return RowAction.BLOCKED
    return RowAction.CREATE
