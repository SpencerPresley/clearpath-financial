import hashlib
from datetime import date
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from pytest_django import Settings

from accounts.models import User
from audit.models import Event
from checks.engine import CheckResult, FindingDraft
from checks.services import PersistedChecks
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import (
    AttachmentKind,
    Channel,
    CheckStatus,
    EventType,
    FindingSource,
    ItemStatus,
    Market,
    Product,
    RiskTier,
    Severity,
    VersionOrigin,
)
from core.errors import InvalidInput, NotFound, NotPermitted
from reviews.models import Attachment, Comment, ReviewItem, Version
from reviews.services import (
    AttachmentOwner,
    ItemFieldChanges,
    NewComment,
    SubmitItemInput,
    add_attachment,
    add_comment,
    submit_item,
    update_item_fields,
)
from reviews.tests.factories import make_item, make_partner, make_version

COPY = "Rates from 7.49% APR. Checking your rate won't affect your credit score."


def _input(**overrides: object) -> SubmitItemInput:
    fields: dict[str, object] = {
        "title": "Spring PL email",
        "product": Product.PERSONAL_LOAN,
        "channel": Channel.EMAIL,
        "markets": (Market.NATIONAL, Market.CA),
        "content_text": COPY,
        "planned_first_run": date(2026, 11, 1),
        "tags": ("spring", "email"),
    }
    fields.update(overrides)
    return SubmitItemInput(**fields)  # pyrefly: ignore[bad-argument-type]


# --- submit_item: the reference action -------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_item_creates_item_v1_and_event(marketer: User, clock: FixedClock) -> None:
    result = submit_item(actor=marketer, data=_input(), clock=clock)

    item = ReviewItem.objects.get(pk=result.item_id)
    version = Version.objects.get(pk=result.version_id)
    assert (item.status, item.round, item.risk_tier) == (ItemStatus.SUBMITTED, 1, RiskTier.LOW)
    assert item.llm_check_status == CheckStatus.PENDING
    assert item.owner == marketer
    assert item.current_version == version
    assert (item.submitted_at, item.created_at, item.updated_at) == (clock.now(), clock.now(), clock.now())
    assert item.markets == ["national", "CA"]
    assert item.tags == ["spring", "email"]
    assert (version.n, version.content_text, version.origin) == (1, COPY, VersionOrigin.SUBMISSION)
    assert version.content_sha256 == Version.hash_content(COPY)

    event = Event.objects.get(pk=result.event_id)
    assert event.type == EventType.ITEM_SUBMITTED
    assert (event.entity, event.entity_id, event.item_id) == ("item", item.pk, item.pk)  # pyrefly: ignore[missing-attribute]
    assert (event.from_status, event.to_status) == (None, "submitted")
    assert event.actor == marketer
    assert event.payload == {
        "version_id": version.pk,
        "version_n": 1,
        "round": 1,
        "risk_tier": "low",
        "content_sha256": version.content_sha256,
    }
    assert result.status is ItemStatus.SUBMITTED


@pytest.mark.django_db
def test_submit_derives_high_tier_for_partner_content(marketer: User, clock: FixedClock) -> None:
    partner = make_partner()

    result = submit_item(
        actor=marketer, data=_input(channel=Channel.AFFILIATE_PAGE, partner_id=partner.pk), clock=clock
    )

    assert result.risk_tier is RiskTier.HIGH
    assert ReviewItem.objects.get(pk=result.item_id).partner == partner


@pytest.mark.django_db
def test_submit_requires_marketer(reviewer: User, clock: FixedClock) -> None:
    with pytest.raises(NotPermitted):
        submit_item(actor=reviewer, data=_input(), clock=clock)

    assert not ReviewItem.objects.exists()


@pytest.mark.django_db
def test_submit_affiliate_without_partner_is_invalid_input(marketer: User, clock: FixedClock) -> None:
    with pytest.raises(InvalidInput) as caught:
        submit_item(actor=marketer, data=_input(channel=Channel.AFFILIATE_PAGE), clock=clock)

    assert caught.value.fields[0].loc == ("body", "partner_id")


@pytest.mark.django_db
def test_submit_with_unknown_partner_is_not_found(marketer: User, clock: FixedClock) -> None:
    with pytest.raises(NotFound):
        submit_item(actor=marketer, data=_input(partner_id=999_999), clock=clock)


@pytest.mark.django_db
def test_submit_rejects_run_dates_out_of_order(marketer: User, clock: FixedClock) -> None:
    with pytest.raises(InvalidInput):
        submit_item(
            actor=marketer,
            data=_input(planned_first_run=date(2026, 11, 2), planned_last_run=date(2026, 11, 1)),
            clock=clock,
        )


@pytest.mark.django_db
def test_submit_rolls_back_item_and_event_together(
    marketer: User, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(**kwargs: object) -> None:
        raise RuntimeError("checks crashed")

    monkeypatch.setattr("reviews.services.run_code_checks", explode)

    with pytest.raises(RuntimeError):
        submit_item(actor=marketer, data=_input(), clock=clock)

    assert not ReviewItem.objects.exists()
    assert not Version.objects.exists()
    assert not Event.objects.exists()


@pytest.mark.django_db
def test_submit_takes_open_findings_count_from_the_checks_seam(
    marketer: User, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The seam knows how many findings stay open after carrying dismissals forward (ruling 4); submit_item
    # must not recount the raw drafts.
    drafts = tuple(
        FindingDraft(
            rule_id=f"R{n}",
            source=FindingSource.CODE,
            severity=Severity.BLOCKING,
            message="x",
            citation="Reg Z",
            suggested_fix=None,
            span=None,
            quote=None,
        )
        for n in range(3)
    )

    def two_open(**kwargs: object) -> PersistedChecks:
        return PersistedChecks(result=CheckResult(findings=drafts, terms_refs=()), open_findings_count=2)

    monkeypatch.setattr("reviews.services.run_code_checks", two_open)

    result = submit_item(actor=marketer, data=_input(), clock=clock)

    assert result.open_findings_count == 2
    assert ReviewItem.objects.get(pk=result.item_id).open_findings_count == 2


# --- inline field edits ----------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_update_item_fields_records_one_event_per_kind(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer, tags=["a"], notes="", risk_tier=RiskTier.LOW)

    update_item_fields(
        actor=reviewer,
        item_id=item.pk,
        changes=ItemFieldChanges(tags=("a", "b"), notes="Check footer", risk_tier=RiskTier.HIGH),
        clock=clock,
    )

    item.refresh_from_db()
    assert (item.tags, item.notes, item.risk_tier, item.risk_tier_overridden) == (
        ["a", "b"],
        "Check footer",
        "high",
        True,
    )
    types = list(Event.objects.filter(item=item).order_by("id").values_list("type", "payload"))
    assert types == [
        (
            "item.fields_updated",
            {
                "changes": [
                    {"field": "tags", "before": ["a"], "after": ["a", "b"]},
                    {"field": "notes", "before": "", "after": "Check footer"},
                ]
            },
        ),
        ("item.risk_tier_overridden", {"before": "low", "after": "high"}),
    ]


@pytest.mark.django_db
def test_update_item_fields_no_op_writes_nothing(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer, tags=["a"])

    update_item_fields(actor=marketer, item_id=item.pk, changes=ItemFieldChanges(tags=("a",)), clock=clock)

    assert not Event.objects.exists()


@pytest.mark.django_db
def test_marketer_cannot_override_risk_tier(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer)

    with pytest.raises(NotPermitted):
        update_item_fields(
            actor=marketer, item_id=item.pk, changes=ItemFieldChanges(risk_tier=RiskTier.HIGH), clock=clock
        )


@pytest.mark.django_db
def test_other_marketer_cannot_edit_tags(marketer: User, user_factory: UserFactory, clock: FixedClock) -> None:
    item = make_item(marketer)
    stranger = user_factory()

    with pytest.raises(NotPermitted):
        update_item_fields(actor=stranger, item_id=item.pk, changes=ItemFieldChanges(tags=("x",)), clock=clock)


# --- comments --------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_comment_on_current_version_records_mentions(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer)
    version = make_version(item, COPY)

    comment_id = add_comment(
        actor=reviewer,
        item_id=item.pk,
        data=NewComment(body="Is this soft pull only?", span_start=22, span_end=48, mention_user_ids=(marketer.pk,)),
        clock=clock,
    )

    comment = Comment.objects.get(pk=comment_id)
    assert comment.version == version
    assert list(comment.mentions.all()) == [marketer]
    event = Event.objects.get(type=EventType.COMMENT_ADDED)
    assert event.payload == {"comment_id": comment_id, "version_id": version.pk, "mention_user_ids": [marketer.pk]}


@pytest.mark.django_db
def test_add_comment_span_must_fit_the_text(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer)
    make_version(item, "short")

    with pytest.raises(InvalidInput):
        add_comment(actor=reviewer, item_id=item.pk, data=NewComment(body="x", span_start=0, span_end=50), clock=clock)


@pytest.mark.django_db
def test_add_comment_unknown_mention_is_invalid(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer)
    make_version(item)

    with pytest.raises(InvalidInput):
        add_comment(
            actor=reviewer, item_id=item.pk, data=NewComment(body="hi", mention_user_ids=(999_999,)), clock=clock
        )


# --- attachments -----------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_attachment_hashes_and_records(
    marketer: User, clock: FixedClock, settings: Settings, tmp_path: Path
) -> None:
    settings.MEDIA_ROOT = tmp_path
    item = make_item(marketer)
    upload = SimpleUploadedFile("memo.pdf", b"substantiation memo", content_type="application/pdf")

    ref = add_attachment(
        actor=marketer,
        owner=AttachmentOwner(kind="item", id=item.pk),
        kind=AttachmentKind.SUBSTANTIATION,
        file=upload,
        clock=clock,
    )

    attachment = Attachment.objects.get(pk=ref.id)
    assert attachment.sha256 == hashlib.sha256(b"substantiation memo").hexdigest()
    assert attachment.sha256 == ref.sha256
    assert (attachment.size_bytes, attachment.original_name, attachment.item_id) == (19, "memo.pdf", item.pk)  # pyrefly: ignore[missing-attribute]
    assert attachment.file.read() == b"substantiation memo"
    event = Event.objects.get(type=EventType.ATTACHMENT_ADDED)
    assert event.payload["owner_type"] == "item"
    assert event.item_id == item.pk  # pyrefly: ignore[missing-attribute]
