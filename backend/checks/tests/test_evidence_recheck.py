"""Attaching evidence re-runs the code checks on the current version (orchestrator ruling on PR #25)."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from pytest_django import Settings

from accounts.models import User
from audit.models import Event
from checks.models import Finding
from checks.services import accept_finding, dismiss_finding
from core.clock import FixedClock
from core.domain import AttachmentKind, EventType, FindingSource, FindingState, ItemStatus
from reviews.models import ReviewItem
from reviews.services import AttachmentOwner, add_attachment
from reviews.tests.conftest import Submit

CREDIT_COPY = "Personal loans from ClearPath. Checking your rate won't affect your credit score."
CREDIT_RULE = "claims.credit_impact"


@pytest.fixture(autouse=True)
def _media(settings: Settings, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path


def _attach(actor: User, item_id: int, clock: FixedClock, kind: AttachmentKind = AttachmentKind.SUBSTANTIATION) -> None:
    add_attachment(
        actor=actor,
        owner=AttachmentOwner(kind="item", id=item_id),
        kind=kind,
        file=SimpleUploadedFile("memo.pdf", b"memo", content_type="application/pdf"),
        clock=clock,
    )


def _credit(item_id: int) -> Finding:
    item = ReviewItem.objects.get(pk=item_id)
    return Finding.objects.get(version_id=item.current_version_id, rule_id=CREDIT_RULE)  # pyrefly: ignore[missing-attribute]


def _checks_runs(item_id: int) -> int:
    return Event.objects.filter(item_id=item_id, type=EventType.CHECKS_COMPLETED).count()


@pytest.mark.django_db
def test_evidence_closes_the_open_finding_it_answers(submit: Submit, marketer: User, clock: FixedClock) -> None:
    item_id = submit(content_text=CREDIT_COPY).item_id
    assert _credit(item_id).state == FindingState.OPEN
    before = ReviewItem.objects.get(pk=item_id).open_findings_count

    _attach(marketer, item_id, clock)

    finding = _credit(item_id)
    assert (finding.state, finding.reason, finding.resolved_by_id, finding.resolved_at) == (  # pyrefly: ignore[missing-attribute]
        FindingState.DISMISSED,
        "Resolved: Substantiation attached",
        None,
        clock.now(),
    )
    event = Event.objects.get(type=EventType.FINDING_DISMISSED, entity_id=finding.pk)
    assert (event.actor_id, event.payload["reason"]) == (None, "Resolved: Substantiation attached")  # pyrefly: ignore[missing-attribute]
    assert _checks_runs(item_id) == 2
    assert ReviewItem.objects.get(pk=item_id).open_findings_count == before - 1


@pytest.mark.django_db
def test_triaged_findings_stay_as_they_are(submit: Submit, marketer: User, lead: User, clock: FixedClock) -> None:
    accepted_id = submit(content_text=CREDIT_COPY).item_id
    accept_finding(actor=lead, finding_id=_credit(accepted_id).pk, clock=clock)
    dismissed_id = submit(content_text=CREDIT_COPY).item_id
    dismiss_finding(actor=lead, finding_id=_credit(dismissed_id).pk, reason="Soft pull only", clock=clock)

    _attach(marketer, accepted_id, clock)
    _attach(marketer, dismissed_id, clock)

    assert _credit(accepted_id).state == FindingState.ACCEPTED
    dismissed = _credit(dismissed_id)
    assert (dismissed.reason, dismissed.resolved_by_id) == ("Soft pull only", lead.pk)  # pyrefly: ignore[missing-attribute]


@pytest.mark.django_db
def test_unrelated_evidence_closes_nothing(submit: Submit, marketer: User, clock: FixedClock) -> None:
    item_id = submit(content_text=CREDIT_COPY).item_id

    _attach(marketer, item_id, clock, kind=AttachmentKind.SCREENSHOT)

    assert _credit(item_id).state == FindingState.OPEN
    assert _checks_runs(item_id) == 2  # still re-checked


@pytest.mark.django_db
def test_the_recheck_adds_new_findings(submit: Submit, marketer: User, clock: FixedClock) -> None:
    item_id = submit(content_text="Guaranteed approval. " + CREDIT_COPY).item_id
    Finding.objects.filter(version__item_id=item_id, rule_id="claims.guaranteed").delete()  # as if the rule were new

    _attach(marketer, item_id, clock)

    item = ReviewItem.objects.get(pk=item_id)
    new = Finding.objects.get(version_id=item.current_version_id, rule_id="claims.guaranteed")  # pyrefly: ignore[missing-attribute]
    assert (new.state, new.source) == (FindingState.OPEN, FindingSource.CODE)
    assert item.open_findings_count == Finding.objects.filter(version_id=item.current_version_id, state="open").count()  # pyrefly: ignore[missing-attribute]


@pytest.mark.django_db
def test_evidence_on_a_version_also_rechecks(submit: Submit, marketer: User, clock: FixedClock) -> None:
    result = submit(content_text=CREDIT_COPY)

    add_attachment(
        actor=marketer,
        owner=AttachmentOwner(kind="version", id=result.version_id),
        kind=AttachmentKind.SUBSTANTIATION,
        file=SimpleUploadedFile("memo.pdf", b"memo"),
        clock=clock,
    )

    assert _credit(result.item_id).state == FindingState.DISMISSED


@pytest.mark.django_db
@pytest.mark.parametrize("status", [ItemStatus.CHANGES_REQUESTED, ItemStatus.APPROVED, ItemStatus.WITHDRAWN])
def test_no_recheck_outside_review(submit: Submit, marketer: User, clock: FixedClock, status: ItemStatus) -> None:
    item_id = submit(content_text=CREDIT_COPY).item_id
    ReviewItem.objects.filter(pk=item_id).update(status=status)

    _attach(marketer, item_id, clock)

    assert _credit(item_id).state == FindingState.OPEN
    assert _checks_runs(item_id) == 1
