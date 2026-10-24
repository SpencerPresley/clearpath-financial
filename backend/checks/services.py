"""Running checks and persisting their results.

The only writer of Finding, TermsRef, and CheckRun, and of `ReviewItem.open_findings_count` (the count of open
findings on the item's current version). Code checks run synchronously inside the calling action's
transaction; `preview_checks` runs the same rules on unsaved text and stores nothing.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final, Self

from django.db import transaction
from django.db.models import Q

from accounts.models import User
from audit.payloads import (
    ChecksCompletedPayload,
    FindingAcceptedPayload,
    FindingDismissedPayload,
    FindingReopenedPayload,
)
from audit.services import record_event
from checks.engine import (
    ENGINE_VERSION,
    RULESET_VERSION,
    CheckResult,
    FindingDraft,
    RuleContext,
    TermsRefDraft,
    human_checklist,
)
from checks.engine import run_code_checks as run_engine
from checks.models import CheckRun, Finding, TermsRef
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import (
    AttachmentKind,
    Channel,
    CheckStatus,
    CreditCardTerms,
    EntityType,
    EventType,
    FindingSource,
    FindingState,
    ItemStatus,
    Market,
    PartnerType,
    PersonalLoanTerms,
    Product,
    Severity,
    TermsField,
    VersionOrigin,
)
from core.errors import InvalidInput, InvalidTransition, NotFound
from partners.models import Partner
from reviews.assignment import locked_item, require_reviewer_of
from reviews.errors import FindingStateConflict, StaleVersion
from reviews.models import Attachment, ReviewItem, Version
from reviews.transitions import start_review
from terms.models import OfferTerms

# What a check result was computed with: the law's date and the engine's behavior (ledger ruling: cache keys
# carry ENGINE_VERSION too, so a regex fix invalidates stored results even when the law hasn't moved).
RULESET_KEY: Final = f"{RULESET_VERSION.isoformat()}/{ENGINE_VERSION}"


@dataclass(frozen=True)
class PersistedChecks:
    """What `run_code_checks` stored for a version.

    `open_findings_count` is the count after carrying identical dismissals forward (ruling 4), so it can be
    lower than `len(result.findings)`. The caller writes it to `ReviewItem.open_findings_count`.
    """

    result: CheckResult
    open_findings_count: int

    @classmethod
    def empty(cls) -> Self:
        return cls(result=CheckResult(findings=(), terms_refs=()), open_findings_count=0)


# --- context ---------------------------------------------------------------------------------------------------


def _current_terms(product: Product, clock: Clock) -> OfferTerms | None:
    return OfferTerms.objects.filter(product=product, effective_range__contains=clock.now()).first()


def _typed(terms: OfferTerms | None) -> PersonalLoanTerms | CreditCardTerms | None:
    return terms.typed_values if terms is not None else None


def _attachment_kinds(version: Version) -> frozenset[AttachmentKind]:
    kinds = Attachment.objects.filter(Q(item_id=version.item.pk) | Q(version__item_id=version.item.pk)).values_list(
        "kind", flat=True
    )
    return frozenset(AttachmentKind(k) for k in kinds)


def _context(version: Version, terms: OfferTerms | None, clock: Clock) -> RuleContext:
    item = version.item
    return RuleContext(
        text=version.content_text,
        product=Product(item.product),
        channel=Channel(item.channel),
        markets=frozenset(Market(m) for m in item.markets),
        partner_type=PartnerType(item.partner.type) if item.partner is not None else None,
        attachment_kinds=_attachment_kinds(version),
        terms=_typed(terms),
        today=clock.today(),
    )


def rule_context(*, version: Version, clock: Clock = SYSTEM_CLOCK) -> RuleContext:
    """What the rules see for a stored version: its item's facts, evidence kinds, and the terms in effect now."""
    return _context(version, _current_terms(Product(version.item.product), clock), clock)


# --- persistence -----------------------------------------------------------------------------------------------


def _span(draft: FindingDraft) -> tuple[int | None, int | None, str | None]:
    # The engine allows an empty span; Finding requires end > start, and an empty quote points at nothing.
    if draft.span is None or draft.span.end <= draft.span.start:
        return None, None, None
    return draft.span.start, draft.span.end, draft.quote


# Human checklist items have no quote, so (rule, None) would match on every later version: a Reg B imagery
# dismissal on v1 would silently cover a changed creative on v5. They carry only into versions whose creative
# can't have changed: the reviewer's own edit and the generated fast-track version (text-only changes).
_HUMAN_CARRIES_INTO: Final = frozenset({VersionOrigin.REVIEWER_EDIT, VersionOrigin.FAST_TRACK})


def _carryable_dismissals(version: Version) -> dict[tuple[str, str | None], Finding]:
    """Per (rule, quote): the dismissal to carry into `version`, if the latest earlier version that raised that
    (rule, quote) left every such finding dismissed. A later accept or reopen of the same finding wins over an
    older dismissal (a reviewer's "this is a real problem" must not be undone by history)."""
    earlier = (
        Finding.objects.filter(version__item_id=version.item.pk, version__n__lt=version.n)
        .select_related("resolved_by", "version")
        .defer("version__content_text", "version__search_vector")
        .order_by("version__n", "pk")
    )
    latest: dict[tuple[str, str | None], tuple[int, list[Finding]]] = {}
    for f in earlier:
        key = (f.rule_id, f.quote)
        n, found = latest.get(key, (f.version.n, []))
        if f.version.n > n:
            n, found = f.version.n, []
        found.append(f)
        latest[key] = (n, found)
    human_ok = VersionOrigin(version.origin) in _HUMAN_CARRIES_INTO
    return {
        key: found[-1]
        for key, (_, found) in latest.items()
        if all(f.state == FindingState.DISMISSED for f in found)
        and (human_ok or found[-1].source != FindingSource.HUMAN)
    }


def persist_findings(*, version: Version, drafts: Sequence[FindingDraft], clock: Clock = SYSTEM_CLOCK) -> int:
    """Store findings on `version`, carrying identical dismissals forward (spec §4.2 ruling 4). Returns the number
    of findings created.

    A finding with the same rule and the same quote (both None for a spanless finding) as one whose latest earlier
    occurrence is dismissed is created dismissed, with the original reason and resolver, `carried_from` set, and a
    FINDING_DISMISSED event (`carried=True`, no actor). Human checklist items carry only into reviewer-edit and
    fast-track versions (see `_HUMAN_CARRIES_INTO`). Drafts that collide on the unique key
    `(source, rule_id, span)`, within the batch or with rows already on the version, are skipped: the first wins.
    """
    now = clock.now()
    carry = _carryable_dismissals(version)
    existing = set(Finding.objects.filter(version=version).values_list("source", "rule_id", "span_start", "span_end"))
    created = 0
    for draft in drafts:
        start, end, quote = _span(draft)
        key = (str(draft.source), draft.rule_id, start, end)
        if key in existing:
            continue
        existing.add(key)
        source = carry.get((draft.rule_id, quote))
        finding = Finding.objects.create(
            version=version,
            rule_id=draft.rule_id,
            citation=draft.citation,
            source=draft.source,
            severity=draft.severity,
            span_start=start,
            span_end=end,
            quote=quote,
            message=draft.message,
            suggested_fix=draft.suggested_fix or "",
            created_at=now,
            **(
                {
                    "state": FindingState.DISMISSED,
                    "reason": source.reason,
                    "resolved_by": source.resolved_by,
                    "resolved_at": now,
                    "carried_from": source,
                }
                if source is not None
                else {}
            ),
        )
        created += 1
        if source is not None:
            record_event(
                type=EventType.FINDING_DISMISSED,
                entity=EntityType.FINDING,
                entity_id=finding.pk,
                item_id=version.item.pk,
                payload=FindingDismissedPayload(
                    finding_id=finding.pk,
                    version_id=version.pk,
                    rule_id=finding.rule_id,
                    reason=finding.reason,
                    carried=True,
                ),
                actor=None,
                at=now,
            )
    return created


def _persist_refs(version: Version, refs: Sequence[TermsRefDraft], terms: OfferTerms | None) -> None:
    if terms is None:
        return
    seen: set[tuple[int, int, str]] = set()
    rows = []
    for ref in refs:
        key = (ref.span.start, ref.span.end, ref.field)
        if ref.span.end <= ref.span.start or key in seen:
            continue
        seen.add(key)
        rows.append(
            TermsRef(
                version=version,
                offer_terms=terms,
                field=TermsField(ref.field),
                span_start=ref.span.start,
                span_end=ref.span.end,
                quote=version.content_text[ref.span.start : ref.span.end],
                quoted_value=ref.quoted_value,
            )
        )
    # A re-run (reaffirm) keeps the refs already recorded: they say which terms the approved text quoted.
    TermsRef.objects.bulk_create(rows, ignore_conflicts=True)


def open_count(version: Version) -> int:
    return Finding.objects.filter(version=version, state=FindingState.OPEN.value).count()


def run_code_checks(*, version: Version, clock: Clock = SYSTEM_CLOCK) -> PersistedChecks:
    """Run the code rules and the human checklist on `version` and persist the results, in the caller's
    transaction: Findings (carrying identical dismissals), TermsRefs to the OfferTerms row in effect, one
    CheckRun, and a CHECKS_COMPLETED event. Returns the open count on the version.

    Safe to re-run on a version (reaffirm re-checks against current rules): existing findings and refs win the
    unique keys, so only new problems are added. The CheckRun is a record, never a cache: the rule context
    (channel, markets, evidence, terms) isn't part of its key.
    """
    now = clock.now()
    terms = _current_terms(Product(version.item.product), clock)
    ctx = _context(version, terms, clock)
    result = run_engine(ctx)
    checklist = human_checklist(ctx)
    drafts = (*result.findings, *checklist)
    persist_findings(version=version, drafts=drafts, clock=clock)
    _persist_refs(version, result.terms_refs, terms)
    CheckRun.objects.create(
        version=version,
        source=FindingSource.CODE,
        status=CheckStatus.SUCCEEDED,
        content_sha256=version.content_sha256,
        ruleset_key=RULESET_KEY,
        started_at=now,
        finished_at=now,
        findings_count=len(result.findings),
    )
    record_event(
        type=EventType.CHECKS_COMPLETED,
        entity=EntityType.VERSION,
        entity_id=version.pk,
        item_id=version.item.pk,
        payload=ChecksCompletedPayload(
            version_id=version.pk,
            source=FindingSource.CODE,
            findings_count=len(drafts),
            blocking_count=sum(1 for d in drafts if d.severity is Severity.BLOCKING),
            ruleset_key=RULESET_KEY,
        ),
        actor=None,
        at=now,
    )
    return PersistedChecks(
        result=CheckResult(findings=drafts, terms_refs=result.terms_refs), open_findings_count=open_count(version)
    )


def recount_open_findings(*, item_id: int) -> int:
    """Write the open-finding count of the item's current version to the item and return it. For actions that
    change findings outside a version-creating action (triage, D2's LLM findings)."""
    item = ReviewItem.objects.only("pk", "current_version").get(pk=item_id)
    count = (
        Finding.objects.filter(version_id=item.current_version_id, state=FindingState.OPEN.value).count()  # pyrefly: ignore[missing-attribute]
        if item.current_version_id is not None  # pyrefly: ignore[missing-attribute]
        else 0
    )
    ReviewItem.objects.filter(pk=item_id).update(open_findings_count=count)
    return count


# --- evidence attached after submit ----------------------------------------------------------------------------

RECHECK_STATUSES: Final = frozenset({ItemStatus.SUBMITTED, ItemStatus.IN_REVIEW, ItemStatus.NEEDS_REREVIEW})


def _fired(ctx: RuleContext) -> set[tuple[str, str]]:
    return {(str(d.source), d.rule_id) for d in (*run_engine(ctx).findings, *human_checklist(ctx))}


def _new_kind(item_id: int, kind: AttachmentKind) -> bool:
    """Whether the attachment just added is the item's first of its kind (only then can it change a rule)."""
    of_item = Q(item_id=item_id) | Q(version__item_id=item_id)
    return Attachment.objects.filter(of_item, kind=kind).count() == 1


def recheck_for_evidence(*, item_id: int, kind: AttachmentKind, clock: Clock = SYSTEM_CLOCK) -> int | None:
    """After an evidence file of `kind` is attached, re-run the code checks on the item's current version, in
    the caller's transaction. Returns the new open count, or None if the item isn't under review.

    Only while the item is reviewable (submitted, in_review, needs_rereview). New findings are added. An open
    code or checklist finding whose rule fired without the new evidence and doesn't fire with it is dismissed by
    the system ("Resolved: <kind> attached", no resolver, FINDING_DISMISSED with no actor). Accepted and
    reviewer-dismissed findings, and AI findings, are left alone. Records CHECKS_COMPLETED and writes the item's
    `open_findings_count`.
    """
    item = locked_item(item_id)
    if ItemStatus(item.status) not in RECHECK_STATUSES or item.current_version_id is None:  # pyrefly: ignore[missing-attribute]
        return None
    version = Version.objects.select_related("item__partner").get(pk=item.current_version_id)  # pyrefly: ignore[missing-attribute]
    now = clock.now()
    answered: set[tuple[str, str]] = set()
    if _new_kind(item_id, kind):
        after = rule_context(version=version, clock=clock)
        before = replace(after, attachment_kinds=after.attachment_kinds - {kind})
        answered = _fired(before) - _fired(after)
    reason = f"Resolved: {kind.value.replace('_', ' ').capitalize()} attached"
    stale = Finding.objects.filter(version=version, state=FindingState.OPEN.value).exclude(source=FindingSource.LLM)
    for finding in stale:
        if (finding.source, finding.rule_id) not in answered:
            continue
        finding.state, finding.reason, finding.resolved_at = FindingState.DISMISSED, reason, now
        finding.save(update_fields=["state", "reason", "resolved_at"])
        record_event(
            type=EventType.FINDING_DISMISSED,
            entity=EntityType.FINDING,
            entity_id=finding.pk,
            item_id=item_id,
            payload=FindingDismissedPayload(
                finding_id=finding.pk, version_id=version.pk, rule_id=finding.rule_id, reason=reason, carried=False
            ),
            actor=None,
            at=now,
        )
    run_code_checks(version=version, clock=clock)
    return recount_open_findings(item_id=item_id)


# --- live preview ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PreviewInput:
    content_text: str
    product: Product
    channel: Channel
    markets: tuple[Market, ...]
    partner_id: int | None = None
    attachment_kinds: tuple[AttachmentKind, ...] = ()


@dataclass(frozen=True)
class PreviewResult:
    findings: tuple[FindingDraft, ...]
    terms_refs: tuple[TermsRefDraft, ...]
    ruleset_key: str


def preview_checks(*, data: PreviewInput, clock: Clock = SYSTEM_CLOCK) -> PreviewResult:
    """Code findings and terms claims for unsaved copy, for the intake form as the marketer types (spec §4.3:
    under 300 ms). Stores nothing; two reads (partner, current terms) plus the engine's few milliseconds.

    Human checklist items are left out: they're the reviewer's, and the marketer can't act on them.
    """
    partner_type: PartnerType | None = None
    if data.partner_id is not None:
        partner = Partner.objects.filter(pk=data.partner_id).only("type").first()
        if partner is None:
            raise NotFound.entity("partner", data.partner_id)
        partner_type = PartnerType(partner.type)
    ctx = RuleContext(
        text=data.content_text,
        product=data.product,
        channel=data.channel,
        markets=frozenset(data.markets),
        partner_type=partner_type,
        attachment_kinds=frozenset(data.attachment_kinds),
        terms=_typed(_current_terms(data.product, clock)),
        today=clock.today(),
    )
    result = run_engine(ctx)
    return PreviewResult(findings=result.findings, terms_refs=result.terms_refs, ruleset_key=RULESET_KEY)


# --- triage ----------------------------------------------------------------------------------------------------

# Where findings can be triaged: the item is waiting for, or in, review. needs_rereview included: a fast-track
# version's findings are triaged there before a fast-track approve (ruling 4).
TRIAGEABLE: Final = frozenset({ItemStatus.SUBMITTED, ItemStatus.IN_REVIEW, ItemStatus.NEEDS_REREVIEW})

# action -> the states it moves a finding from; the target is the action's own state.
_FINDING_SOURCES: Final = {
    FindingState.ACCEPTED: frozenset({FindingState.OPEN, FindingState.DISMISSED}),
    FindingState.DISMISSED: frozenset({FindingState.OPEN, FindingState.ACCEPTED}),
    FindingState.OPEN: frozenset({FindingState.ACCEPTED, FindingState.DISMISSED}),
}
_ACTION_WORD: Final = {FindingState.ACCEPTED: "accept", FindingState.DISMISSED: "dismiss", FindingState.OPEN: "reopen"}


def _triage(*, actor: User, finding_id: int, to: FindingState, text: str, clock: Clock) -> None:
    """Move one finding on the item's current version, then recount. Only the assignee or a lead, never the
    owner. A first triage on a `submitted` item starts the review (submitted -> in_review)."""
    action = _ACTION_WORD[to]
    finding = Finding.objects.select_related("version").filter(pk=finding_id).first()
    if finding is None:
        raise NotFound.entity("finding", finding_id)
    now = clock.now()
    with transaction.atomic():
        item = locked_item(finding.version.item.pk)
        require_reviewer_of(actor, item)
        status = ItemStatus(item.status)
        if status not in TRIAGEABLE:
            raise InvalidTransition(action=f"{action}_finding", from_status=status)
        current = item.current_version
        if current is None or current.pk != finding.version.pk:
            raise StaleVersion(version_n=finding.version.n, current_n=current.n if current else None)
        finding = Finding.objects.select_for_update().get(pk=finding_id)
        state = FindingState(finding.state)
        if state not in _FINDING_SOURCES[to]:
            raise FindingStateConflict(action=action, state=state)
        if status is ItemStatus.SUBMITTED:
            start_review(item, reviewer=actor, at=now)
        finding.state = to
        finding.carried_from = None
        if to is FindingState.OPEN:
            finding.reason, finding.resolved_by, finding.resolved_at = "", None, None
        else:
            finding.reason, finding.resolved_by, finding.resolved_at = text, actor, now
        finding.save(update_fields=["state", "carried_from", "reason", "resolved_by", "resolved_at"])
        common = {"finding_id": finding.pk, "version_id": current.pk, "rule_id": finding.rule_id}
        if to is FindingState.ACCEPTED:
            event_type, payload = EventType.FINDING_ACCEPTED, FindingAcceptedPayload(**common, note=text)
        elif to is FindingState.DISMISSED:
            event_type, payload = EventType.FINDING_DISMISSED, FindingDismissedPayload(**common, reason=text)
        else:
            event_type, payload = EventType.FINDING_REOPENED, FindingReopenedPayload(**common)
        record_event(
            type=event_type,
            entity=EntityType.FINDING,
            entity_id=finding.pk,
            item_id=item.pk,
            payload=payload,
            actor=actor,
            at=now,
        )
        recount_open_findings(item_id=item.pk)


def accept_finding(*, actor: User, finding_id: int, note: str = "", clock: Clock = SYSTEM_CLOCK) -> None:
    """The problem is real: it becomes a required change (product-spec "Automation")."""
    _triage(actor=actor, finding_id=finding_id, to=FindingState.ACCEPTED, text=note.strip(), clock=clock)


def dismiss_finding(*, actor: User, finding_id: int, reason: str, clock: Clock = SYSTEM_CLOCK) -> None:
    """Not a problem here, and why. The reason is required (the DB check is the backstop)."""
    if not reason.strip():
        raise InvalidInput.for_field("reason", "Say why this isn't a problem.")
    _triage(actor=actor, finding_id=finding_id, to=FindingState.DISMISSED, text=reason.strip(), clock=clock)


def reopen_finding(*, actor: User, finding_id: int, clock: Clock = SYSTEM_CLOCK) -> None:
    _triage(actor=actor, finding_id=finding_id, to=FindingState.OPEN, text="", clock=clock)
