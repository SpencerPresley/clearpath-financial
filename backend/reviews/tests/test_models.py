from datetime import date
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.db import IntegrityError, connection, transaction
from pytest_django import Settings

from accounts.models import User
from core.db import constraint_name
from core.domain import (
    AttachmentKind,
    Channel,
    DecisionLane,
    DecisionOutcome,
    ExpiryRule,
    ItemStatus,
    ReopenReason,
    RiskTier,
)
from reviews.models import Attachment, Comment, Decision, ExpiryPolicy, Placement, ReviewItem, Version
from reviews.tests.factories import AT, make_item, make_partner, make_version


def _raw(sql: str, params: list[int]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


@pytest.mark.django_db
def test_item_key_is_display_format(marketer: User) -> None:
    item = make_item(marketer)

    assert item.key == f"CP-{item.pk}"


@pytest.mark.django_db
def test_version_unique_per_item_n(marketer: User) -> None:
    item = make_item(marketer)
    make_version(item, n=1)

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        make_version(item, "Different text", n=1)

    assert constraint_name(caught.value) == "version_unique_n_per_item"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sql",
    ["UPDATE reviews_version SET content_text = 'edited' WHERE id = %s", "DELETE FROM reviews_version WHERE id = %s"],
)
def test_version_rejects_update_and_delete(marketer: User, sql: str) -> None:
    version = make_version(make_item(marketer))

    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        _raw(sql, [version.pk])


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sql",
    ["UPDATE reviews_decision SET reason = 'edited' WHERE id = %s", "DELETE FROM reviews_decision WHERE id = %s"],
)
def test_decision_rejects_update_and_delete(marketer: User, reviewer: User, sql: str) -> None:
    item = make_item(marketer)
    version = make_version(item)
    decision = Decision.objects.create(
        item=item,
        version=version,
        outcome=DecisionOutcome.CHANGES_REQUESTED,
        lane=DecisionLane.STANDARD,
        approver=reviewer,
        reason="Add the APR range.",
        ruleset_date=date(2026, 10, 1),
        decided_at=AT,
    )

    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        _raw(sql, [decision.pk])


@pytest.mark.django_db
def test_approval_needs_an_expiry(marketer: User, reviewer: User) -> None:
    item = make_item(marketer)
    version = make_version(item)

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        Decision.objects.create(
            item=item,
            version=version,
            outcome=DecisionOutcome.APPROVED,
            lane=DecisionLane.STANDARD,
            approver=reviewer,
            reason="Clean.",
            ruleset_date=date(2026, 10, 1),
            decided_at=AT,
        )

    assert constraint_name(caught.value) == "decision_approval_has_expiry"


@pytest.mark.django_db
def test_decision_reason_required(marketer: User, reviewer: User) -> None:
    item = make_item(marketer)
    version = make_version(item)

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        Decision.objects.create(
            item=item,
            version=version,
            outcome=DecisionOutcome.REJECTED,
            lane=DecisionLane.STANDARD,
            approver=reviewer,
            reason="   ",
            ruleset_date=date(2026, 10, 1),
            decided_at=AT,
        )

    assert constraint_name(caught.value) == "decision_reason_required"


def _attachment(**owners: object) -> Attachment:
    return Attachment(
        kind=AttachmentKind.SUBSTANTIATION,
        file=ContentFile(b"memo", name="memo.pdf"),
        original_name="memo.pdf",
        content_type="application/pdf",
        size_bytes=4,
        sha256="0" * 64,
        uploaded_at=AT,
        **owners,
    )


@pytest.mark.django_db
def test_attachment_requires_exactly_one_owner(marketer: User, settings: Settings, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path
    item = make_item(marketer)
    partner = make_partner()

    for owners in ({}, {"item": item, "partner": partner}):
        with pytest.raises(IntegrityError) as caught, transaction.atomic():
            _attachment(uploaded_by=marketer, **owners).save()
        assert constraint_name(caught.value) == "attachment_one_owner"

    _attachment(uploaded_by=marketer, partner=partner).save()


@pytest.mark.django_db
def test_attachment_rejects_update(marketer: User, settings: Settings, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path
    attachment = _attachment(uploaded_by=marketer, item=make_item(marketer))
    attachment.save()

    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        _raw("UPDATE reviews_attachment SET kind = 'other' WHERE id = %s", [attachment.pk])


@pytest.mark.django_db
def test_affiliate_item_requires_partner_unless_legacy(marketer: User) -> None:
    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        make_item(marketer, channel=Channel.AFFILIATE_PAGE)
    assert constraint_name(caught.value) == "item_partner_channel_has_partner"

    make_item(marketer, channel=Channel.AFFILIATE_PAGE, partner=make_partner())
    make_item(marketer, channel=Channel.AFFILIATE_PAGE, is_legacy=True, legacy_ref="REQ-1")


@pytest.mark.django_db
def test_legacy_ref_unique_but_nullable(marketer: User) -> None:
    make_item(marketer)
    make_item(marketer)
    make_item(marketer, is_legacy=True, legacy_ref="REQ-0042")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_item(marketer, is_legacy=True, legacy_ref="REQ-0042")


@pytest.mark.django_db
def test_non_legacy_item_needs_owner_and_market(marketer: User) -> None:
    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        make_item(marketer, markets=[])
    assert constraint_name(caught.value) == "item_has_market_unless_legacy"

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        make_item(None)
    assert constraint_name(caught.value) == "item_has_owner_unless_legacy"

    make_item(None, markets=[], is_legacy=True, legacy_ref="REQ-7")


@pytest.mark.django_db
def test_planned_run_dates_ordered(marketer: User) -> None:
    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        make_item(marketer, planned_first_run=date(2026, 11, 2), planned_last_run=date(2026, 11, 1))

    assert constraint_name(caught.value) == "item_planned_run_ordered"


@pytest.mark.django_db
def test_needs_rereview_requires_a_reopen_reason(marketer: User) -> None:
    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        make_item(marketer, status=ItemStatus.NEEDS_REREVIEW)

    assert constraint_name(caught.value) == "item_rereview_has_reason"


@pytest.mark.django_db
def test_queue_priority_puts_rereview_first_then_tier(marketer: User) -> None:
    rereview_low = make_item(
        marketer, status=ItemStatus.NEEDS_REREVIEW, reopen_reason=ReopenReason.TERMS_CHANGED, risk_tier=RiskTier.LOW
    )
    submitted_high = make_item(marketer, status=ItemStatus.SUBMITTED, risk_tier=RiskTier.HIGH)
    submitted_medium = make_item(marketer, status=ItemStatus.SUBMITTED, risk_tier=RiskTier.MEDIUM)

    ordered = list(ReviewItem.objects.order_by("queue_priority").values_list("pk", flat=True))

    assert ordered == [rereview_low.pk, submitted_high.pk, submitted_medium.pk]


@pytest.mark.django_db
def test_rereview_keeps_priority_once_a_reviewer_opens_it(marketer: User) -> None:
    # needs_rereview -> in_review is allowed; the item is still live content at risk.
    reopened_in_review = make_item(
        marketer, status=ItemStatus.IN_REVIEW, reopen_reason=ReopenReason.TERMS_CHANGED, risk_tier=RiskTier.LOW
    )
    # A re-review sent back for changes and resubmitted is still live content waiting on review.
    resubmitted_rereview = make_item(
        marketer, status=ItemStatus.SUBMITTED, reopen_reason=ReopenReason.TERMS_CHANGED, risk_tier=RiskTier.LOW
    )
    fresh_high = make_item(marketer, status=ItemStatus.SUBMITTED, risk_tier=RiskTier.HIGH)
    expired = make_item(
        marketer, status=ItemStatus.EXPIRED, reopen_reason=ReopenReason.TERMS_CHANGED, risk_tier=RiskTier.HIGH
    )

    ordered = list(ReviewItem.objects.order_by("queue_priority", "pk").values_list("pk", flat=True))

    rereviews_last = max(ordered.index(reopened_in_review.pk), ordered.index(resubmitted_rereview.pk))
    assert rereviews_last < ordered.index(fresh_high.pk) < ordered.index(expired.pk)


@pytest.mark.django_db
def test_decision_version_must_belong_to_the_item(marketer: User, reviewer: User) -> None:
    item, other = make_item(marketer), make_item(marketer)
    make_version(item)
    foreign = make_version(other)

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        Decision.objects.create(
            item=item,
            version=foreign,
            outcome=DecisionOutcome.REJECTED,
            lane=DecisionLane.STANDARD,
            approver=reviewer,
            reason="No.",
            ruleset_date=date(2026, 10, 1),
            decided_at=AT,
        )

    assert constraint_name(caught.value) == "decision_version_same_item"


@pytest.mark.django_db
def test_placement_and_current_version_must_belong_to_the_item(marketer: User) -> None:
    item, other = make_item(marketer), make_item(marketer)
    foreign = make_version(other)

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        Placement.objects.create(
            item=item,
            approved_version=foreign,
            location="x",
            first_run=date(2026, 11, 1),
            created_by=marketer,
            created_at=AT,
        )
    assert constraint_name(caught.value) == "placement_version_same_item"

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        ReviewItem.objects.filter(pk=item.pk).update(current_version=foreign)
    assert constraint_name(caught.value) == "item_current_version_same_item"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("column", "sql"),
    [
        ("title", "SELECT id FROM reviews_reviewitem WHERE UPPER(title::text) LIKE UPPER(%s)"),
        ("content_text", "SELECT id FROM reviews_version WHERE UPPER(content_text::text) LIKE UPPER(%s)"),
    ],
)
def test_case_insensitive_contains_uses_a_trigram_index(column: str, sql: str) -> None:
    # Django compiles icontains to UPPER(col::text) LIKE UPPER(%s); the index must be on that expression.
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(f"EXPLAIN {sql}", ["%loan%"])
        plan = "\n".join(row[0] for row in cursor.fetchall())

    assert "trgm" in plan, plan


@pytest.mark.django_db
def test_version_search_vector_is_generated(marketer: User) -> None:
    version = make_version(make_item(marketer), "Checking your rate won't affect your credit score.")

    hits = Version.objects.filter(search_vector="credit scores").values_list("pk", flat=True)

    assert list(hits) == [version.pk]


@pytest.mark.django_db
def test_version_hash_must_be_sha256_hex(marketer: User) -> None:
    item = make_item(marketer)

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        make_version(item, content_sha256="abc")

    assert constraint_name(caught.value) == "version_sha256_hex"


@pytest.mark.django_db
def test_comment_span_must_be_ordered(marketer: User) -> None:
    version = make_version(make_item(marketer))

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        Comment.objects.create(version=version, author=marketer, body="Here", span_start=5, span_end=5, created_at=AT)

    assert constraint_name(caught.value) == "comment_span_valid"


@pytest.mark.django_db
def test_placement_last_run_not_before_first(marketer: User) -> None:
    item = make_item(marketer)
    version = make_version(item)

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        Placement.objects.create(
            item=item,
            approved_version=version,
            location="Partner blog",
            first_run=date(2026, 11, 2),
            last_run=date(2026, 11, 1),
            created_by=marketer,
            created_at=AT,
        )

    assert constraint_name(caught.value) == "placement_run_ordered"


@pytest.mark.django_db
def test_expiry_policy_seeded_for_every_channel() -> None:
    policies = {p.channel: p for p in ExpiryPolicy.objects.all()}

    assert set(policies) == {c.value for c in Channel}
    assert policies[Channel.EMAIL].rule == ExpiryRule.SEND_WINDOW
    assert policies[Channel.LANDING_PAGE].months == 12
    assert policies[Channel.AFFILIATE_PAGE].months == 6
