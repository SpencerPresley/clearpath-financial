"""Findings triage: accept, dismiss with a reason, reopen; who may, and on which version."""

import pytest

from accounts.models import User
from audit.models import Event
from checks.models import Finding
from checks.services import accept_finding, dismiss_finding, reopen_finding
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import EventType, FindingState, ItemStatus, Role
from core.errors import InvalidInput, InvalidTransition, NotPermitted
from reviews.errors import FindingStateConflict, StaleVersion
from reviews.models import ReviewItem
from reviews.tests.conftest import Submit
from reviews.tests.factories import make_version


def _blocking(item_id: int) -> Finding:
    return Finding.objects.get(version__item_id=item_id, rule_id="claims.guaranteed")


@pytest.fixture
def item(submit: Submit, reviewer: User) -> ReviewItem:
    result = submit(content_text="Guaranteed approval for personal loans.")
    return ReviewItem.objects.get(pk=result.item_id)


@pytest.mark.django_db
def test_dismiss_records_reason_resolver_event_and_starts_review(
    item: ReviewItem, reviewer: User, clock: FixedClock
) -> None:
    finding = _blocking(item.pk)
    before = item.open_findings_count

    dismiss_finding(actor=reviewer, finding_id=finding.pk, reason="  Footer carries the disclosure ", clock=clock)

    finding.refresh_from_db()
    item.refresh_from_db()
    assert (finding.state, finding.reason, finding.resolved_by, finding.resolved_at) == (
        "dismissed",
        "Footer carries the disclosure",
        reviewer,
        clock.now(),
    )
    assert item.open_findings_count == before - 1
    assert item.status == ItemStatus.IN_REVIEW
    types = list(Event.objects.filter(item_id=item.pk).order_by("-id").values_list("type", flat=True)[:2])
    assert types == [EventType.FINDING_DISMISSED, EventType.ITEM_REVIEW_STARTED]
    event = Event.objects.get(type=EventType.FINDING_DISMISSED, entity_id=finding.pk)
    assert event.payload["reason"] == "Footer carries the disclosure"
    assert event.payload["carried"] is False


@pytest.mark.django_db
def test_accept_then_reopen(item: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    finding = _blocking(item.pk)

    accept_finding(actor=reviewer, finding_id=finding.pk, note="Drop 'guaranteed'", clock=clock)
    finding.refresh_from_db()
    assert (finding.state, finding.reason) == ("accepted", "Drop 'guaranteed'")
    reopen_finding(actor=reviewer, finding_id=finding.pk, clock=clock)

    finding.refresh_from_db()
    assert (finding.state, finding.reason, finding.resolved_by) == ("open", "", None)
    assert [e.type for e in Event.objects.filter(entity_id=finding.pk, entity="finding").order_by("id")] == [
        EventType.FINDING_ACCEPTED,
        EventType.FINDING_REOPENED,
    ]


@pytest.mark.django_db
def test_switching_between_accepted_and_dismissed_is_allowed(
    item: ReviewItem, reviewer: User, clock: FixedClock
) -> None:
    finding = _blocking(item.pk)

    accept_finding(actor=reviewer, finding_id=finding.pk, clock=clock)
    dismiss_finding(actor=reviewer, finding_id=finding.pk, reason="Approved claim on file", clock=clock)

    assert Finding.objects.get(pk=finding.pk).state == FindingState.DISMISSED


@pytest.mark.django_db
def test_same_state_or_reopening_an_open_finding_conflicts(item: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    finding = _blocking(item.pk)

    with pytest.raises(FindingStateConflict):
        reopen_finding(actor=reviewer, finding_id=finding.pk, clock=clock)
    accept_finding(actor=reviewer, finding_id=finding.pk, clock=clock)
    with pytest.raises(FindingStateConflict):
        accept_finding(actor=reviewer, finding_id=finding.pk, clock=clock)


@pytest.mark.django_db
def test_blank_reason_is_rejected_on_the_field(item: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    with pytest.raises(InvalidInput) as caught:
        dismiss_finding(actor=reviewer, finding_id=_blocking(item.pk).pk, reason="   ", clock=clock)

    assert caught.value.fields[0].loc == ("body", "reason")


@pytest.mark.django_db
def test_only_the_assignee_or_a_lead_triages(
    item: ReviewItem, user_factory: UserFactory, marketer: User, lead: User, clock: FixedClock
) -> None:
    other = user_factory(roles=[Role.REVIEWER])
    finding = _blocking(item.pk)

    for actor in (other, marketer):
        with pytest.raises(NotPermitted):
            dismiss_finding(actor=actor, finding_id=finding.pk, reason="x", clock=clock)
    dismiss_finding(actor=lead, finding_id=finding.pk, reason="Lead call", clock=clock)


@pytest.mark.django_db
def test_findings_on_an_old_version_or_a_decided_item_are_frozen(
    item: ReviewItem, reviewer: User, clock: FixedClock
) -> None:
    finding = _blocking(item.pk)
    make_version(item, "v2 copy", n=2)

    with pytest.raises(StaleVersion):
        dismiss_finding(actor=reviewer, finding_id=finding.pk, reason="x", clock=clock)
    ReviewItem.objects.filter(pk=item.pk).update(status=ItemStatus.APPROVED)
    with pytest.raises(InvalidTransition):
        dismiss_finding(actor=reviewer, finding_id=finding.pk, reason="x", clock=clock)
