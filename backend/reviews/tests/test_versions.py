"""Resubmission, new rounds, and generated versions."""

from datetime import timedelta

import pytest
from django.db import transaction

from accounts.models import User
from audit.models import Event
from checks.models import Finding
from core.clock import FixedClock
from core.domain import CheckStatus, EventType, ItemStatus, ReopenReason, VersionOrigin
from core.errors import InvalidTransition, NotPermitted
from reviews.models import ReviewItem, Version
from reviews.tests.conftest import Submit
from reviews.tests.factories import make_item, make_version
from reviews.versions import create_version, resubmit_item, start_new_round


def _types(item_id: int, after: int = 0) -> list[str]:
    return list(Event.objects.filter(item_id=item_id, pk__gt=after).order_by("id").values_list("type", flat=True))


@pytest.mark.django_db
def test_resubmit_creates_v2_bumps_the_round_and_goes_back_to_the_reviewer(
    submit: Submit, marketer: User, reviewer: User, clock: FixedClock
) -> None:
    first = submit()
    assert ReviewItem.objects.get(pk=first.item_id).assignee == reviewer
    ReviewItem.objects.filter(pk=first.item_id).update(
        status=ItemStatus.CHANGES_REQUESTED, llm_check_status=CheckStatus.SUCCEEDED
    )
    clock.advance(timedelta(days=2))
    before = Event.objects.order_by("-id").first()
    assert before is not None

    result = resubmit_item(
        actor=marketer, item_id=first.item_id, content_text="Guaranteed approval.", note="Tightened", clock=clock
    )

    item = ReviewItem.objects.get(pk=first.item_id)
    version = Version.objects.get(pk=result.version_id)
    assert (item.status, item.round, item.current_version, item.submitted_at) == (
        ItemStatus.SUBMITTED,
        2,
        version,
        clock.now(),
    )
    assert (version.n, version.origin, version.based_on_id) == (2, VersionOrigin.SUBMISSION, first.version_id)  # pyrefly: ignore[missing-attribute]
    assert item.llm_check_status == CheckStatus.PENDING
    assert item.open_findings_count == Finding.objects.filter(version=version, state="open").count() > 0
    assert _types(item.pk, before.pk) == ["item.resubmitted", "checks.completed", "item.assigned"]
    resubmitted = Event.objects.get(pk=result.event_id)
    assert (resubmitted.from_status, resubmitted.to_status) == ("changes_requested", "submitted")
    assert resubmitted.payload == {
        "version_id": version.pk,
        "version_n": 2,
        "round": 2,
        "previous_version_id": first.version_id,
        "note": "Tightened",
    }
    assigned = Event.objects.filter(item_id=item.pk, type=EventType.ITEM_ASSIGNED).latest("id")
    assert (assigned.payload["mode"], assigned.payload["assignee_id"]) == ("sticky", reviewer.pk)


@pytest.mark.django_db
def test_only_the_owner_resubmits_and_only_after_changes_requested(
    marketer: User, user_factory: object, clock: FixedClock
) -> None:
    other = user_factory()  # pyrefly: ignore[not-callable]
    pending = make_item(marketer, status=ItemStatus.IN_REVIEW)
    make_version(pending)
    asked = make_item(marketer, status=ItemStatus.CHANGES_REQUESTED)
    make_version(asked)

    with pytest.raises(InvalidTransition):
        resubmit_item(actor=marketer, item_id=pending.pk, content_text="x", clock=clock)
    with pytest.raises(NotPermitted):
        resubmit_item(actor=other, item_id=asked.pk, content_text="x", clock=clock)

    assert Version.objects.filter(item=asked).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("status", [ItemStatus.WITHDRAWN, ItemStatus.EXPIRED])
def test_new_round_copies_the_current_version_and_clears_the_reopen_reason(
    marketer: User, clock: FixedClock, status: ItemStatus
) -> None:
    item = make_item(marketer, status=status, reopen_reason=ReopenReason.TERMS_CHANGED, round=2)
    make_version(item, "Rates from 8.99% APR.", n=1)
    generated = make_version(item, "Rates from 9.49% APR.", n=2, origin=VersionOrigin.FAST_TRACK)

    result = start_new_round(actor=marketer, item_id=item.pk, clock=clock)

    item.refresh_from_db()
    version = Version.objects.get(pk=result.version_id)
    assert (item.status, item.round, item.reopen_reason) == (ItemStatus.SUBMITTED, 3, None)
    assert (version.n, version.content_text, version.based_on, version.author) == (
        3,
        "Rates from 9.49% APR.",
        generated,
        marketer,
    )
    started = Event.objects.get(pk=result.event_id)
    assert (started.type, started.from_status, started.to_status) == ("item.new_round_started", status, "submitted")


@pytest.mark.django_db
def test_new_round_takes_new_copy(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer, status=ItemStatus.WITHDRAWN)
    make_version(item)

    result = start_new_round(actor=marketer, item_id=item.pk, content_text="Fresh copy.", clock=clock)

    assert Version.objects.get(pk=result.version_id).content_text == "Fresh copy."


@pytest.mark.django_db
def test_new_round_from_approved_is_invalid(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer, status=ItemStatus.APPROVED)
    make_version(item)

    with pytest.raises(InvalidTransition):
        start_new_round(actor=marketer, item_id=item.pk, clock=clock)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("origin", "llm"),
    [(VersionOrigin.FAST_TRACK, CheckStatus.SKIPPED), (VersionOrigin.REVIEWER_EDIT, CheckStatus.FAILED)],
)
def test_generated_versions_record_version_created_and_their_ai_status(
    marketer: User, reviewer: User, clock: FixedClock, origin: VersionOrigin, llm: CheckStatus
) -> None:
    item = make_item(marketer, status=ItemStatus.IN_REVIEW, llm_check_status=CheckStatus.FAILED)
    base = make_version(item)

    with transaction.atomic():
        created = create_version(item=item, text="Edited.", author=reviewer, origin=origin, based_on=base, clock=clock)

    item.refresh_from_db()
    assert (item.status, item.current_version, item.llm_check_status) == (ItemStatus.IN_REVIEW, created.version, llm)
    event = Event.objects.get(type=EventType.VERSION_CREATED)
    assert event.payload == {
        "version_id": created.version.pk,
        "version_n": 2,
        "origin": origin.value,
        "based_on_version_id": base.pk,
    }
    assert item.open_findings_count == created.checks.open_findings_count
