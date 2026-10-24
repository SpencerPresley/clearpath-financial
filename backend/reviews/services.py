"""Review-item actions. The only place items, versions, comments, and attachments change.

Each action: check permission, validate business rules, write rows plus an Event in one transaction, and
return a typed result. `submit_item` is the reference implementation other actions copy.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Literal

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from accounts.models import User
from audit.payloads import (
    AttachmentAddedPayload,
    CommentAddedPayload,
    FieldChange,
    ItemFieldsUpdatedPayload,
    ItemRiskTierOverriddenPayload,
    ItemSubmittedPayload,
)
from audit.services import record_event
from checks.services import run_code_checks
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import (
    PARTNER_CHANNELS,
    AttachmentKind,
    Channel,
    CheckStatus,
    EntityType,
    EventType,
    ItemStatus,
    Market,
    Product,
    RiskTier,
    Role,
    VersionOrigin,
)
from core.errors import InvalidInput, NotFound, NotPermitted
from core.permissions import REVIEW_ROLES, has_role, require_role
from partners.models import Partner
from reviews.assignment import auto_assign
from reviews.filters import ItemFilter, ItemSort
from reviews.models import Attachment, Comment, ReviewItem, SavedView, Version
from reviews.risk import derive_risk_tier

# --- submit ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SubmitItemInput:
    title: str
    product: Product
    channel: Channel
    markets: tuple[Market, ...]
    content_text: str
    planned_first_run: date
    planned_last_run: date | None = None
    partner_id: int | None = None
    is_prescreen: bool = False
    source_url: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SubmitItemResult:
    item_id: int
    version_id: int
    version_n: int
    status: ItemStatus
    risk_tier: RiskTier
    llm_check_status: CheckStatus
    open_findings_count: int
    event_id: int


def _resolve_partner(data: SubmitItemInput) -> Partner | None:
    if data.partner_id is None:
        if data.channel in PARTNER_CHANNELS:
            raise InvalidInput.for_field("partner_id", "Pick the partner that publishes this.")
        return None
    partner = Partner.objects.filter(pk=data.partner_id).first()
    if partner is None:
        raise NotFound.entity("partner", data.partner_id)
    return partner


def submit_item(*, actor: User, data: SubmitItemInput, clock: Clock = SYSTEM_CLOCK) -> SubmitItemResult:
    """A marketer submits new content: creates the item in `submitted` with v1, records ITEM_SUBMITTED, runs code
    checks, and auto-assigns a reviewer (ITEM_ASSIGNED). The LLM pre-review is started by an outbox handler on
    ITEM_SUBMITTED (workstream D)."""
    require_role(actor, Role.MARKETER)
    if data.planned_last_run is not None and data.planned_last_run < data.planned_first_run:
        raise InvalidInput.for_field("planned_last_run", "The last run date is before the first run date.")
    partner = _resolve_partner(data)
    risk_tier = derive_risk_tier(
        product=data.product, channel=data.channel, has_partner=partner is not None, is_prescreen=data.is_prescreen
    )
    now = clock.now()

    with transaction.atomic():
        item = ReviewItem.objects.create(
            title=data.title,
            product=data.product,
            channel=data.channel,
            partner=partner,
            markets=list(dict.fromkeys(data.markets)),
            owner=actor,
            status=ItemStatus.SUBMITTED,
            round=1,
            risk_tier=risk_tier,
            is_prescreen=data.is_prescreen,
            llm_check_status=CheckStatus.PENDING,
            tags=list(dict.fromkeys(data.tags)),
            planned_first_run=data.planned_first_run,
            planned_last_run=data.planned_last_run,
            source_url=data.source_url or "",
            submitted_at=now,
            created_at=now,
            updated_at=now,
        )
        version = Version.objects.create(
            item=item,
            n=1,
            content_text=data.content_text,
            content_sha256=Version.hash_content(data.content_text),
            author=actor,
            origin=VersionOrigin.SUBMISSION,
            created_at=now,
        )
        item.current_version = version
        item.save(update_fields=["current_version"])
        event = record_event(
            type=EventType.ITEM_SUBMITTED,
            entity=EntityType.ITEM,
            entity_id=item.pk,
            item_id=item.pk,
            payload=ItemSubmittedPayload(
                version_id=version.pk,
                version_n=1,
                round=1,
                risk_tier=risk_tier,
                content_sha256=version.content_sha256,
            ),
            actor=actor,
            at=now,
            to_status=ItemStatus.SUBMITTED,
        )
        checks = run_code_checks(version=version, clock=clock)
        item.open_findings_count = checks.open_findings_count
        item.save(update_fields=["open_findings_count"])
        auto_assign(item=item, actor=actor, clock=clock)

    return SubmitItemResult(
        item_id=item.pk,
        version_id=version.pk,
        version_n=1,
        status=ItemStatus.SUBMITTED,
        risk_tier=risk_tier,
        llm_check_status=CheckStatus.PENDING,
        open_findings_count=item.open_findings_count,
        event_id=event.pk,
    )


# --- inline edits ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemFieldChanges:
    """Low-stakes fields edited inline in the queue. None means "leave as is"."""

    tags: tuple[str, ...] | None = None
    notes: str | None = None
    risk_tier: RiskTier | None = None


def _locked_item(item_id: int) -> ReviewItem:
    item = ReviewItem.objects.select_for_update().filter(pk=item_id).first()
    if item is None:
        raise NotFound.entity("item", item_id)
    return item


def _require_owner_or_reviewer(actor: User, item: ReviewItem) -> None:
    if item.owner_id != actor.pk and not has_role(actor, *REVIEW_ROLES):  # pyrefly: ignore[missing-attribute]
        raise NotPermitted("Only the submitter or a reviewer can change this item.")


def update_item_fields(*, actor: User, item_id: int, changes: ItemFieldChanges, clock: Clock = SYSTEM_CLOCK) -> None:
    """Tags and notes: the submitter or a reviewer. Risk tier: reviewers and leads only (an override)."""
    if changes.risk_tier is not None:
        require_role(actor, *REVIEW_ROLES)
    now = clock.now()
    with transaction.atomic():
        item = _locked_item(item_id)
        _require_owner_or_reviewer(actor, item)
        field_changes: list[FieldChange] = []
        if changes.tags is not None:
            tags = list(dict.fromkeys(changes.tags))
            if tags != item.tags:
                field_changes.append(FieldChange(field="tags", before=list(item.tags), after=tags))
                item.tags = tags
        if changes.notes is not None and changes.notes != item.notes:
            field_changes.append(FieldChange(field="notes", before=item.notes, after=changes.notes))
            item.notes = changes.notes
        tier_before = RiskTier(item.risk_tier)
        tier_changed = changes.risk_tier is not None and changes.risk_tier is not tier_before
        if not field_changes and not tier_changed:
            return
        item.updated_at = now
        if field_changes:
            record_event(
                type=EventType.ITEM_FIELDS_UPDATED,
                entity=EntityType.ITEM,
                entity_id=item.pk,
                item_id=item.pk,
                payload=ItemFieldsUpdatedPayload(changes=tuple(field_changes)),
                actor=actor,
                at=now,
            )
        if tier_changed and changes.risk_tier is not None:
            item.risk_tier = changes.risk_tier
            item.risk_tier_overridden = True
            record_event(
                type=EventType.ITEM_RISK_TIER_OVERRIDDEN,
                entity=EntityType.ITEM,
                entity_id=item.pk,
                item_id=item.pk,
                payload=ItemRiskTierOverriddenPayload(before=tier_before, after=changes.risk_tier),
                actor=actor,
                at=now,
            )
        item.save(update_fields=["tags", "notes", "risk_tier", "risk_tier_overridden", "updated_at"])


# --- comments --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class NewComment:
    body: str
    version_n: int | None = None  # None: the current version
    span_start: int | None = None
    span_end: int | None = None
    mention_user_ids: tuple[int, ...] = ()


def add_comment(*, actor: User, item_id: int, data: NewComment, clock: Clock = SYSTEM_CLOCK) -> int:
    """Comment on a version, optionally anchored to a span and @mentioning colleagues. Returns the comment id."""
    item = ReviewItem.objects.filter(pk=item_id).first()
    if item is None:
        raise NotFound.entity("item", item_id)
    _require_owner_or_reviewer(actor, item)
    versions = Version.objects.filter(item=item)
    version = (
        versions.filter(n=data.version_n).first() if data.version_n is not None else versions.order_by("-n").first()
    )
    if version is None:
        raise NotFound.entity("version", data.version_n or 0)
    if (data.span_start is None) != (data.span_end is None):
        raise InvalidInput.for_field("span_end", "A span needs both a start and an end.")
    in_text = data.span_start is None or (
        data.span_end is not None and 0 <= data.span_start < data.span_end <= len(version.content_text)
    )
    if not in_text:
        raise InvalidInput.for_field("span_end", "The highlighted range is outside the text.")
    mentions = tuple(dict.fromkeys(data.mention_user_ids))
    mentioned = list(User.objects.filter(pk__in=mentions, is_active=True))
    if len(mentioned) != len(mentions):
        raise InvalidInput.for_field("mention_user_ids", "Some mentioned people don't exist.")
    now = clock.now()
    with transaction.atomic():
        comment = Comment.objects.create(
            version=version,
            author=actor,
            body=data.body,
            span_start=data.span_start,
            span_end=data.span_end,
            created_at=now,
        )
        comment.mentions.set(mentioned)
        record_event(
            type=EventType.COMMENT_ADDED,
            entity=EntityType.COMMENT,
            entity_id=comment.pk,
            item_id=item.pk,
            payload=CommentAddedPayload(comment_id=comment.pk, version_id=version.pk, mention_user_ids=mentions),
            actor=actor,
            at=now,
        )
    return comment.pk


# --- attachments -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AttachmentOwner:
    """What an uploaded file is attached to. Decision evidence is attached by the decision service."""

    kind: Literal["item", "version", "partner"]
    id: int


@dataclass(frozen=True)
class AttachmentRef:
    id: int
    sha256: str


def _sha256(file: UploadedFile) -> str:
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()


def add_attachment(
    *, actor: User, owner: AttachmentOwner, kind: AttachmentKind, file: UploadedFile, clock: Clock = SYSTEM_CLOCK
) -> AttachmentRef:
    """Store an evidence file with its hash. Immutable: replacing a file adds a new attachment."""
    item_id: int | None = None
    owner_fields: dict[str, ReviewItem | Version | Partner]
    if owner.kind == "partner":
        require_role(actor, Role.LEAD)
        partner = Partner.objects.filter(pk=owner.id).first()
        if partner is None:
            raise NotFound.entity("partner", owner.id)
        owner_fields = {"partner": partner}
    elif owner.kind == "version":
        version = Version.objects.select_related("item").filter(pk=owner.id).first()
        if version is None:
            raise NotFound.entity("version", owner.id)
        _require_owner_or_reviewer(actor, version.item)
        item_id = version.item.pk
        owner_fields = {"version": version}
    else:
        item = ReviewItem.objects.filter(pk=owner.id).first()
        if item is None:
            raise NotFound.entity("item", owner.id)
        _require_owner_or_reviewer(actor, item)
        item_id = item.pk
        owner_fields = {"item": item}

    sha256 = _sha256(file)
    now = clock.now()
    with transaction.atomic():
        attachment = Attachment.objects.create(
            kind=kind,
            file=file,
            original_name=file.name or "upload",
            content_type=file.content_type or "application/octet-stream",
            size_bytes=file.size or 0,
            sha256=sha256,
            uploaded_by=actor,
            uploaded_at=now,
            **owner_fields,  # pyrefly: ignore[bad-argument-type]
        )
        record_event(
            type=EventType.ATTACHMENT_ADDED,
            entity=EntityType.ATTACHMENT,
            entity_id=attachment.pk,
            item_id=item_id,
            payload=AttachmentAddedPayload(
                attachment_id=attachment.pk, kind=kind, sha256=sha256, owner_type=owner.kind, owner_id=owner.id
            ),
            actor=actor,
            at=now,
        )
    return AttachmentRef(id=attachment.pk, sha256=sha256)


# --- saved views (personal UI preferences: no event) -----------------------------------------------------------


@dataclass(frozen=True)
class NewSavedView:
    name: str
    filters: ItemFilter
    sort: ItemSort
    columns: tuple[str, ...] = ()


def create_saved_view(*, actor: User, data: NewSavedView, clock: Clock = SYSTEM_CLOCK) -> int:
    if SavedView.objects.filter(owner=actor, name=data.name).exists():
        raise InvalidInput.for_field("name", "You already have a view with this name.")
    view = SavedView.objects.create(
        owner=actor,
        name=data.name,
        filters=data.filters.model_dump(mode="json"),
        sort=data.sort.value,
        columns=list(data.columns),
        created_at=clock.now(),
    )
    return view.pk


def delete_saved_view(*, actor: User, view_id: int) -> None:
    deleted, _ = SavedView.objects.filter(owner=actor, pk=view_id).delete()
    if not deleted:
        raise NotFound.entity("saved view", view_id)
