"""Reads for one item's record: detail, versions, diff, history, comments, attachments, placements,
decisions. Split from `reviews.selectors` (the queue) to keep each file about one screen."""

from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Count, Prefetch, Q, QuerySet
from django.urls import reverse

from accounts.models import User
from audit.models import Event
from audit.outbox import EventRecord
from audit.payloads import EventPayload, LlmCheckFailedPayload
from checks.models import TermsRef
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import (
    AttachmentKind,
    CheckStatus,
    DecisionLane,
    DecisionOutcome,
    EntityType,
    EventType,
    ItemStatus,
    LlmFailureCode,
    Product,
    Role,
    TakedownState,
    TermsField,
    VersionOrigin,
)
from core.errors import NotFound, NotPermitted
from core.permissions import has_role
from reviews.diff import DiffSegment, diff_texts
from reviews.filters import ItemFilter, ItemSort
from reviews.models import Attachment, Comment, Decision, Placement, ReviewItem, SavedView, Version
from reviews.selectors import DecisionSummary, ItemRow, PartyRef, item_row, live_placements_q, row_queryset


def _person(user: User) -> PartyRef:
    return PartyRef(id=user.pk, name=user.display_name or user.email)


def _item_or_404(item_id: int) -> ReviewItem:
    item = ReviewItem.objects.filter(pk=item_id).first()
    if item is None:
        raise NotFound.entity("item", item_id)
    return item


# --- versions --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Span:
    start: int
    end: int


@dataclass(frozen=True)
class OfferTermsRef:
    id: int
    product: Product
    version: int


@dataclass(frozen=True)
class TermsRefRow:
    field: TermsField
    span: Span
    quote: str
    quoted_value: str
    offer_terms: OfferTermsRef


@dataclass(frozen=True)
class VersionSummary:
    id: int
    n: int
    origin: VersionOrigin
    author: PartyRef
    created_at: datetime
    based_on_n: int | None


@dataclass(frozen=True)
class VersionDetail(VersionSummary):
    content_text: str
    content_sha256: str
    terms_refs: tuple[TermsRefRow, ...]


def _summary(version: Version) -> VersionSummary:
    return VersionSummary(
        id=version.pk,
        n=version.n,
        origin=VersionOrigin(version.origin),
        author=_person(version.author),
        created_at=version.created_at,
        based_on_n=version.based_on.n if version.based_on else None,
    )


def _detail(version: Version) -> VersionDetail:
    refs = tuple(
        TermsRefRow(
            field=TermsField(ref.field),
            span=Span(ref.span_start, ref.span_end),
            quote=ref.quote,
            quoted_value=str(ref.quoted_value.normalize()),
            offer_terms=OfferTermsRef(
                id=ref.offer_terms.pk, product=Product(ref.offer_terms.product), version=ref.offer_terms.version
            ),
        )
        for ref in version.terms_refs.all()  # pyrefly: ignore[missing-attribute]  # reverse FK from checks
    )
    s = _summary(version)
    return VersionDetail(
        id=s.id,
        n=s.n,
        origin=s.origin,
        author=s.author,
        created_at=s.created_at,
        based_on_n=s.based_on_n,
        content_text=version.content_text,
        content_sha256=version.content_sha256,
        terms_refs=refs,
    )


def _versions(item_id: int) -> QuerySet[Version]:
    return (
        Version.objects.filter(item_id=item_id)
        .select_related("author", "based_on")
        .defer("search_vector", "content_text", "based_on__content_text", "based_on__search_vector")
        .order_by("n")
    )


def list_versions(*, item_id: int) -> tuple[VersionSummary, ...]:
    _item_or_404(item_id)
    return tuple(_summary(v) for v in _versions(item_id))


def get_version(*, item_id: int, n: int) -> VersionDetail:
    version = (
        Version.objects.filter(item_id=item_id, n=n)
        .select_related("author", "based_on")
        .defer("search_vector")
        .prefetch_related(
            Prefetch("terms_refs", queryset=TermsRef.objects.select_related("offer_terms").order_by("span_start"))
        )
        .first()
    )
    if version is None:
        raise NotFound(
            f"Version {n} of CP-{item_id} doesn't exist.", details={"entity": "version", "item_id": item_id, "n": n}
        )
    return _detail(version)


@dataclass(frozen=True)
class VersionDiff:
    from_n: int
    to_n: int
    segments: tuple[DiffSegment, ...]


def version_diff(*, item_id: int, from_n: int, to_n: int) -> VersionDiff:
    texts = dict(Version.objects.filter(item_id=item_id, n__in=[from_n, to_n]).values_list("n", "content_text"))
    for n in (from_n, to_n):
        if n not in texts:
            raise NotFound(f"Version {n} of CP-{item_id} doesn't exist.", details={"entity": "version", "n": n})
    return VersionDiff(from_n=from_n, to_n=to_n, segments=diff_texts(texts[from_n], texts[to_n]))


# --- decisions -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    attachment_id: int
    sha256: str
    kind: AttachmentKind
    original_name: str


@dataclass(frozen=True)
class DecisionRow(DecisionSummary):  # outcome, reason, decided_at
    id: int
    version_n: int
    lane: DecisionLane
    approver: PartyRef
    ruleset_date: date
    engine_version: str
    expires_at: datetime | None
    llm_override_reason: str | None
    ai_review_carried_from_n: int | None
    terms_versions: tuple[OfferTermsRef, ...]
    evidence: tuple[Evidence, ...]


def _decisions(item_id: int) -> QuerySet[Decision]:
    return (
        Decision.objects.filter(item_id=item_id)
        .select_related("approver", "version", "ai_review_carried_from")
        .defer(
            "version__content_text",
            "version__search_vector",
            "ai_review_carried_from__content_text",
            "ai_review_carried_from__search_vector",
        )
        .prefetch_related("terms_versions", "evidence__attachment")
        .order_by("-decided_at", "-pk")
    )


def _decision_row(d: Decision) -> DecisionRow:
    return DecisionRow(
        id=d.pk,
        version_n=d.version.n,
        outcome=DecisionOutcome(d.outcome),
        lane=DecisionLane(d.lane),
        approver=_person(d.approver),
        reason=d.reason,
        ruleset_date=d.ruleset_date,
        engine_version=d.engine_version,
        expires_at=d.expires_at,
        llm_override_reason=d.llm_override_reason or None,
        ai_review_carried_from_n=d.ai_review_carried_from.n if d.ai_review_carried_from else None,
        terms_versions=tuple(
            OfferTermsRef(id=t.pk, product=Product(t.product), version=t.version) for t in d.terms_versions.all()
        ),
        evidence=tuple(
            Evidence(
                attachment_id=e.attachment.pk,
                sha256=e.sha256,
                kind=AttachmentKind(e.attachment.kind),
                original_name=e.attachment.original_name,
            )
            for e in d.evidence.all()
        ),
        decided_at=d.decided_at,
    )


def list_decisions(*, item_id: int) -> tuple[DecisionRow, ...]:
    _item_or_404(item_id)
    return tuple(_decision_row(d) for d in _decisions(item_id))


def get_decision(*, decision_id: int) -> DecisionRow:
    item_id = Decision.objects.filter(pk=decision_id).values_list("item_id", flat=True).first()
    decision = _decisions(item_id).filter(pk=decision_id).first() if item_id is not None else None
    if decision is None:
        raise NotFound.entity("decision", decision_id)
    return _decision_row(decision)


# --- item detail -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemDetail(ItemRow):
    is_prescreen: bool
    risk_tier_overridden: bool
    source_url: str | None
    legacy_ref: str | None
    legacy_submitter: str
    legacy_reviewer: str
    legacy_history: str
    approved_at: datetime | None
    retention_until: date | None
    current_version: VersionDetail | None
    versions: tuple[VersionSummary, ...]
    latest_decision: DecisionRow | None  # the row's summary, as the full record
    live_placements_count: int
    numbers_change: bool | None
    llm_check_failure_code: LlmFailureCode | None
    llm_check_failure_reason: str | None


def _numbers_change(item_id: int, current: VersionDetail | None) -> bool | None:
    """For a generated (fast-track) version only: whether its text differs from the approved text it was rendered
    from, i.e. whether any number the copy quotes changed (terms.impact's `numbers_change`). None otherwise."""
    if current is None or current.origin is not VersionOrigin.FAST_TRACK or current.based_on_n is None:
        return None
    based_on_sha = (
        Version.objects.filter(item_id=item_id, n=current.based_on_n).values_list("content_sha256", flat=True).first()
    )
    return based_on_sha != current.content_sha256


def _llm_failure(
    item_id: int, status: CheckStatus, current: VersionDetail | None
) -> tuple[LlmFailureCode | None, str | None]:
    """Why the current version's AI check failed: the latest LLM_CHECK_FAILED for that version. Nothing unless the
    item's check is `failed` (a retry clears it)."""
    if status is not CheckStatus.FAILED or current is None:
        return None, None
    payload = (
        Event.objects.filter(item_id=item_id, type=EventType.LLM_CHECK_FAILED, payload__version_id=current.id)
        .order_by("-id")
        .values_list("payload", flat=True)
        .first()
    )
    if payload is None:
        return None, None
    failed = LlmCheckFailedPayload.model_validate(payload)
    return failed.code, failed.error


def get_item_detail(*, item_id: int, clock: Clock = SYSTEM_CLOCK) -> ItemDetail:
    today = clock.today()
    item = (
        row_queryset(ReviewItem.objects.filter(pk=item_id))
        .annotate(live_placements_count=Count("placements", filter=live_placements_q(today, "placements__")))
        .first()
    )
    if item is None:
        raise NotFound.entity("item", item_id)
    row = item_row(item, now=clock.now())
    versions = tuple(_summary(v) for v in _versions(item_id))
    current_n = getattr(item, "current_version_n", None)
    current = get_version(item_id=item_id, n=current_n) if isinstance(current_n, int) else None
    latest = next(iter(_decisions(item_id)[:1]), None)
    failure_code, failure_reason = _llm_failure(item_id, row.llm_check_status, current)
    return ItemDetail(
        **{field: getattr(row, field) for field in ItemRow.__dataclass_fields__ if field != "latest_decision"},
        is_prescreen=item.is_prescreen,
        risk_tier_overridden=item.risk_tier_overridden,
        source_url=item.source_url or None,
        legacy_ref=item.legacy_ref,
        legacy_submitter=item.legacy_submitter,
        legacy_reviewer=item.legacy_reviewer,
        legacy_history=item.legacy_history,
        approved_at=item.approved_at,
        retention_until=item.retention_until,
        current_version=current,
        versions=versions,
        latest_decision=_decision_row(latest) if latest else None,
        live_placements_count=item.live_placements_count,  # pyrefly: ignore[missing-attribute]
        numbers_change=_numbers_change(item_id, current),
        llm_check_failure_code=failure_code,
        llm_check_failure_reason=failure_reason,
    )


# --- history ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    type: EventType
    at: datetime
    actor: PartyRef | None
    entity: EntityType
    entity_id: int
    from_status: ItemStatus | None
    to_status: ItemStatus | None
    payload: EventPayload


@dataclass(frozen=True)
class ItemHistory:
    entries: tuple[HistoryEntry, ...]


def item_history(*, item_id: int) -> ItemHistory:
    """The item's event log, oldest first: the History tab, rendered."""
    _item_or_404(item_id)
    events = Event.objects.filter(item_id=item_id).select_related("actor").order_by("id")
    entries = []
    for event in events:
        record = EventRecord.from_event(event)
        entries.append(
            HistoryEntry(
                id=record.id,
                type=record.type,
                at=record.at,
                actor=_person(event.actor) if event.actor else None,
                entity=record.entity,
                entity_id=record.entity_id,
                from_status=record.from_status,
                to_status=record.to_status,
                payload=record.payload,
            )
        )
    return ItemHistory(entries=tuple(entries))


# --- comments --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CommentRow:
    id: int
    version_n: int
    author: PartyRef
    body: str
    span: Span | None
    mentions: tuple[PartyRef, ...]
    created_at: datetime


def list_comments(*, item_id: int, version_n: int | None = None) -> tuple[CommentRow, ...]:
    _item_or_404(item_id)
    qs = Comment.objects.filter(version__item_id=item_id)
    if version_n is not None:
        qs = qs.filter(version__n=version_n)
    rows = (
        qs.select_related("author", "version")
        .defer("version__content_text", "version__search_vector")
        .prefetch_related("mentions")
        .order_by("created_at", "pk")
    )
    return tuple(
        CommentRow(
            id=c.pk,
            version_n=c.version.n,
            author=_person(c.author),
            body=c.body,
            span=Span(c.span_start, c.span_end) if c.span_start is not None and c.span_end is not None else None,
            mentions=tuple(_person(u) for u in c.mentions.all()),
            created_at=c.created_at,
        )
        for c in rows
    )


# --- attachments -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AttachmentRow:
    id: int
    kind: AttachmentKind
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: PartyRef
    uploaded_at: datetime
    download_url: str


def _attachment_row(a: Attachment) -> AttachmentRow:
    return AttachmentRow(
        id=a.pk,
        kind=AttachmentKind(a.kind),
        original_name=a.original_name,
        content_type=a.content_type,
        size_bytes=a.size_bytes,
        sha256=a.sha256,
        uploaded_by=_person(a.uploaded_by),
        uploaded_at=a.uploaded_at,
        download_url=reverse("api:downloadAttachment", kwargs={"attachment_id": a.pk}),
    )


def list_item_attachments(*, item_id: int) -> tuple[AttachmentRow, ...]:
    """Attachments on the item and on any of its versions, newest first."""
    _item_or_404(item_id)
    qs = Attachment.objects.filter(Q(item_id=item_id) | Q(version__item_id=item_id)).select_related("uploaded_by")
    return tuple(_attachment_row(a) for a in qs.order_by("-uploaded_at", "-pk"))


def can_read_partner_attachments(viewer: User) -> bool:
    """Ledger ruling: partner attachments (agreements) are for reviewers, leads, and admins, not marketers.
    Item, version, and decision evidence is readable by anyone who can read the item (every signed-in user)."""
    return has_role(viewer, Role.REVIEWER, Role.ADMIN)


def _require_partner_reader(viewer: User) -> None:
    if not can_read_partner_attachments(viewer):
        raise NotPermitted("Partner agreements and evidence are for reviewers and leads.")


def list_partner_attachments(*, partner_id: int, viewer: User) -> tuple[AttachmentRow, ...]:
    _require_partner_reader(viewer)
    qs = Attachment.objects.filter(partner_id=partner_id).select_related("uploaded_by")
    return tuple(_attachment_row(a) for a in qs.order_by("-uploaded_at", "-pk"))


def get_attachment(*, attachment_id: int, viewer: User) -> Attachment:
    """For the download view only: returns the model so the view can stream the file."""
    attachment = Attachment.objects.filter(pk=attachment_id).first()
    if attachment is None:
        raise NotFound.entity("attachment", attachment_id)
    if attachment.partner_id is not None:  # pyrefly: ignore[missing-attribute]
        _require_partner_reader(viewer)
    return attachment


# --- placements ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlacementRow:
    id: int
    approved_version_n: int
    location: str
    url: str | None
    first_run: date
    last_run: date | None
    monitored: bool
    takedown_state: TakedownState | None
    takedown_requested_at: datetime | None
    takedown_confirmed_at: datetime | None
    is_live: bool
    created_by: PartyRef
    created_at: datetime


def list_placements(*, item_id: int, clock: Clock = SYSTEM_CLOCK) -> tuple[PlacementRow, ...]:
    _item_or_404(item_id)
    today = clock.today()
    live_ids = set(Placement.objects.filter(live_placements_q(today), item_id=item_id).values_list("pk", flat=True))
    qs = (
        Placement.objects.filter(item_id=item_id)
        .select_related("created_by", "approved_version")
        .defer("approved_version__content_text", "approved_version__search_vector")
        .order_by("first_run", "pk")
    )
    return tuple(
        PlacementRow(
            id=p.pk,
            approved_version_n=p.approved_version.n,
            location=p.location,
            url=p.url or None,
            first_run=p.first_run,
            last_run=p.last_run,
            monitored=p.monitored,
            takedown_state=TakedownState(p.takedown_state) if p.takedown_state else None,
            takedown_requested_at=p.takedown_requested_at,
            takedown_confirmed_at=p.takedown_confirmed_at,
            is_live=p.pk in live_ids,
            created_by=_person(p.created_by),
            created_at=p.created_at,
        )
        for p in qs
    )


def get_placement(*, placement_id: int, clock: Clock = SYSTEM_CLOCK) -> PlacementRow:
    item_id = Placement.objects.filter(pk=placement_id).values_list("item_id", flat=True).first()
    row = (
        next((p for p in list_placements(item_id=item_id, clock=clock) if p.id == placement_id), None)
        if item_id
        else None
    )
    if row is None:
        raise NotFound.entity("placement", placement_id)
    return row


# --- saved views -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SavedViewRow:
    id: int
    name: str
    filters: ItemFilter
    sort: ItemSort
    columns: tuple[str, ...]
    created_at: datetime


def _saved_view_row(v: SavedView) -> SavedViewRow:
    return SavedViewRow(
        id=v.pk,
        name=v.name,
        filters=ItemFilter.model_validate(v.filters),
        sort=ItemSort(v.sort),
        columns=tuple(v.columns),
        created_at=v.created_at,
    )


def list_saved_views(*, owner: User) -> tuple[SavedViewRow, ...]:
    return tuple(_saved_view_row(v) for v in SavedView.objects.filter(owner=owner).order_by("name"))


def get_saved_view(*, owner: User, view_id: int) -> SavedViewRow:
    view = SavedView.objects.filter(owner=owner, pk=view_id).first()
    if view is None:
        raise NotFound.entity("saved view", view_id)
    return _saved_view_row(view)
