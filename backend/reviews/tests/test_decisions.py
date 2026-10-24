"""Decisions: gates, what an approval records, approve-with-edits, reaffirm, pull."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from pytest_django import Settings

from accounts.models import User
from audit.models import Event
from checks.engine import ENGINE_VERSION, RULESET_VERSION
from checks.models import Finding
from checks.services import accept_finding, dismiss_finding
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import (
    AttachmentKind,
    Channel,
    CheckStatus,
    DecisionLane,
    DecisionOutcome,
    EventType,
    ItemStatus,
    ReopenReason,
    Role,
    TakedownState,
    VersionOrigin,
)
from core.errors import (
    AiCheckPending,
    Conflict,
    InvalidInput,
    InvalidTransition,
    NotPermitted,
    OpenFindingsBlockDecision,
)
from reviews.decisions import (
    DecisionInput,
    approval_expiry,
    pull_item,
    reaffirm,
    record_decision,
)
from reviews.errors import AcceptedFindingsBlockApproval, FindingsNeedTriage, StaleOfferTerms, StaleVersion
from reviews.models import Decision, ExpiryPolicy, Placement, ReviewItem, Version
from reviews.months import add_months
from reviews.services import AttachmentOwner, add_attachment
from reviews.tests.conftest import RATE_COPY, Submit, ai_done, dismiss_all
from reviews.tests.factories import make_partner
from reviews.versions import create_version
from terms.models import OfferTerms

APPROVE = DecisionOutcome.APPROVED


def _decide(actor: User, item_id: int, clock: FixedClock, **fields: object) -> int:
    item = ReviewItem.objects.select_related("current_version").get(pk=item_id)
    data: dict[str, object] = {
        "outcome": APPROVE,
        "version_n": item.current_version.n if item.current_version else 0,
        "reason": "Meets policy",
    }
    data.update(fields)
    return record_decision(actor=actor, item_id=item_id, data=DecisionInput(**data), clock=clock).decision_id  # pyrefly: ignore[bad-argument-type]


@pytest.fixture
def ready(submit: Submit, reviewer: User, pl_terms: OfferTerms, clock: FixedClock) -> ReviewItem:
    """A landing page quoting PL v1, every finding dismissed, AI check done, in review."""
    result = submit(content_text=RATE_COPY)
    dismiss_all(result.item_id, reviewer, clock)
    ai_done(result.item_id)
    return ReviewItem.objects.get(pk=result.item_id)


# --- approve ---------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_approval_records_what_it_was_approved_against(
    ready: ReviewItem,
    reviewer: User,
    marketer: User,
    pl_terms: OfferTerms,
    clock: FixedClock,
    settings: Settings,
    tmp_path: object,
) -> None:
    settings.MEDIA_ROOT = str(tmp_path)
    memo = add_attachment(
        actor=marketer,
        owner=AttachmentOwner(kind="item", id=ready.pk),
        kind=AttachmentKind.SUBSTANTIATION,
        file=SimpleUploadedFile("memo.pdf", b"rate memo"),
        clock=clock,
    )

    decision_id = _decide(reviewer, ready.pk, clock, evidence_attachment_ids=(memo.id,))

    decision = Decision.objects.get(pk=decision_id)
    item = ReviewItem.objects.get(pk=ready.pk)
    assert (decision.version, decision.outcome, decision.lane, decision.approver) == (
        item.current_version,
        "approved",
        "standard",
        reviewer,
    )
    assert (decision.ruleset_date, decision.engine_version) == (RULESET_VERSION, ENGINE_VERSION)
    assert decision.expires_at == datetime(2027, 10, 24, 15, 0, tzinfo=UTC)  # landing page: 12 months
    assert [t.pk for t in decision.terms_versions.all()] == [pl_terms.pk]
    assert [(e.attachment_id, e.sha256) for e in decision.evidence.all()] == [(memo.id, memo.sha256)]  # pyrefly: ignore[missing-attribute]
    assert decision.ai_review_carried_from is None
    assert (item.status, item.approved_at, item.approval_expires_at) == (
        ItemStatus.APPROVED,
        clock.now(),
        decision.expires_at,
    )
    event = Event.objects.get(type=EventType.DECISION_RECORDED)
    assert (event.entity, event.entity_id, event.from_status, event.to_status) == (
        "decision",
        decision.pk,
        "in_review",
        "approved",
    )
    assert event.payload["terms_version_ids"] == [pl_terms.pk]
    assert event.payload["engine_version"] == ENGINE_VERSION


@pytest.mark.django_db
def test_deciding_a_submitted_item_starts_the_review_first(submit: Submit, reviewer: User, clock: FixedClock) -> None:
    item_id = submit().item_id

    _decide(reviewer, item_id, clock, outcome=DecisionOutcome.REJECTED, reason="Off-brand")

    types = list(Event.objects.filter(item_id=item_id).order_by("-id").values_list("type", flat=True)[:2])
    assert types == [EventType.DECISION_RECORDED, EventType.ITEM_REVIEW_STARTED]
    assert ReviewItem.objects.get(pk=item_id).status == ItemStatus.REJECTED


@pytest.mark.django_db
def test_open_findings_block_approve_and_nothing_is_written(submit: Submit, reviewer: User, clock: FixedClock) -> None:
    item_id = submit(content_text="Guaranteed approval.").item_id
    ai_done(item_id)

    with pytest.raises(OpenFindingsBlockDecision) as caught:
        _decide(reviewer, item_id, clock)

    assert caught.value.details["open_count"] == ReviewItem.objects.get(pk=item_id).open_findings_count
    assert ReviewItem.objects.get(pk=item_id).status == ItemStatus.SUBMITTED  # start_review rolled back too
    assert not Decision.objects.exists()


@pytest.mark.django_db
def test_accepted_findings_block_plain_approve_but_not_request_changes(
    submit: Submit, reviewer: User, clock: FixedClock
) -> None:
    item_id = submit(content_text="Guaranteed approval.").item_id
    ai_done(item_id)
    accept_finding(
        actor=reviewer,
        finding_id=Finding.objects.get(version__item_id=item_id, rule_id="claims.guaranteed").pk,
        clock=clock,
    )
    dismiss_all(item_id, reviewer, clock)

    with pytest.raises(AcceptedFindingsBlockApproval):
        _decide(reviewer, item_id, clock)
    _decide(reviewer, item_id, clock, outcome=DecisionOutcome.CHANGES_REQUESTED, reason="Drop 'guaranteed'")

    assert ReviewItem.objects.get(pk=item_id).status == ItemStatus.CHANGES_REQUESTED


@pytest.mark.django_db
def test_request_changes_and_reject_need_no_triage(submit: Submit, reviewer: User, clock: FixedClock) -> None:
    asked = submit(content_text="Guaranteed approval.").item_id
    rejected = submit(content_text="Guaranteed approval.").item_id

    _decide(reviewer, asked, clock, outcome=DecisionOutcome.CHANGES_REQUESTED)
    _decide(reviewer, rejected, clock, outcome=DecisionOutcome.REJECTED)

    assert ReviewItem.objects.get(pk=asked).status == ItemStatus.CHANGES_REQUESTED
    assert ReviewItem.objects.get(pk=rejected).status == ItemStatus.REJECTED
    assert Decision.objects.get(item_id=asked).expires_at is None


@pytest.mark.django_db
def test_blank_reason_is_refused(ready: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    with pytest.raises(InvalidInput) as caught:
        _decide(reviewer, ready.pk, clock, reason="  ")

    assert caught.value.fields[0].loc == ("body", "reason")


@pytest.mark.django_db
@pytest.mark.parametrize("status", [CheckStatus.PENDING, CheckStatus.RUNNING])
def test_approve_waits_for_the_ai_check(
    ready: ReviewItem, reviewer: User, clock: FixedClock, status: CheckStatus
) -> None:
    ai_done(ready.pk, status)

    with pytest.raises(AiCheckPending):
        _decide(reviewer, ready.pk, clock)
    _decide(reviewer, ready.pk, clock, outcome=DecisionOutcome.CHANGES_REQUESTED)


@pytest.mark.django_db
def test_failed_ai_check_needs_an_override_reason_which_is_recorded(
    ready: ReviewItem, reviewer: User, clock: FixedClock
) -> None:
    ai_done(ready.pk, CheckStatus.FAILED)

    with pytest.raises(InvalidInput) as caught:
        _decide(reviewer, ready.pk, clock)
    assert caught.value.fields[0].loc == ("body", "llm_override_reason")
    decision_id = _decide(reviewer, ready.pk, clock, llm_override_reason="Read it line by line")

    assert Decision.objects.get(pk=decision_id).llm_override_reason == "Read it line by line"


@pytest.mark.django_db
def test_deciding_an_old_version_is_stale(ready: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    with pytest.raises(StaleVersion) as caught:
        _decide(reviewer, ready.pk, clock, version_n=2)

    assert caught.value.details == {"version_n": 2, "current_n": 1}


@pytest.mark.django_db
def test_superseded_offer_terms_block_approval(
    ready: ReviewItem, reviewer: User, lead: User, pl_terms: OfferTerms, clock: FixedClock
) -> None:
    OfferTerms.objects.filter(pk=pl_terms.pk).update(
        effective_range=DateTimeTZRange(pl_terms.effective_range.lower, clock.now(), "[)")  # pyrefly: ignore[missing-attribute]
    )
    OfferTerms.objects.create(
        product="personal_loan",
        version=2,
        effective_range=DateTimeTZRange(clock.now(), None, "[)"),
        values=pl_terms.values,
        created_by=lead,
        created_at=clock.now(),
    )

    with pytest.raises(StaleOfferTerms) as caught:
        _decide(reviewer, ready.pk, clock)

    assert caught.value.details == {"terms_versions": ["personal_loan v1"]}


@pytest.mark.django_db
def test_only_the_assignee_or_a_lead_decides_and_never_the_owner(
    ready: ReviewItem, user_factory: UserFactory, marketer: User, lead: User, clock: FixedClock
) -> None:
    other = user_factory(roles=[Role.REVIEWER])
    User.objects.filter(pk=marketer.pk).update(roles=[Role.MARKETER, Role.LEAD])
    marketer.refresh_from_db()

    for actor in (other, marketer):
        with pytest.raises(NotPermitted):
            _decide(actor, ready.pk, clock)
    _decide(lead, ready.pk, clock)


@pytest.mark.django_db
def test_evidence_must_belong_to_the_item_or_its_partner(
    submit: Submit, reviewer: User, marketer: User, lead: User, clock: FixedClock, settings: Settings, tmp_path: object
) -> None:
    settings.MEDIA_ROOT = str(tmp_path)
    partner = make_partner()
    item_id = submit(channel=Channel.AFFILIATE_PAGE, partner_id=partner.pk).item_id
    other_id = submit().item_id
    dismiss_all(item_id, reviewer, clock)
    ai_done(item_id)
    agreement = add_attachment(
        actor=lead,
        owner=AttachmentOwner(kind="partner", id=partner.pk),
        kind=AttachmentKind.AGREEMENT,
        file=SimpleUploadedFile("agreement.pdf", b"signed"),
        clock=clock,
    )
    stranger = add_attachment(
        actor=marketer,
        owner=AttachmentOwner(kind="item", id=other_id),
        kind=AttachmentKind.OTHER,
        file=SimpleUploadedFile("x.pdf", b"x"),
        clock=clock,
    )

    with pytest.raises(InvalidInput):
        _decide(reviewer, item_id, clock, evidence_attachment_ids=(stranger.id,))
    decision_id = _decide(reviewer, item_id, clock, evidence_attachment_ids=(agreement.id,))

    assert [e.sha256 for e in Decision.objects.get(pk=decision_id).evidence.all()] == [agreement.sha256]


@pytest.mark.django_db
def test_rejected_is_terminal(ready: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    _decide(reviewer, ready.pk, clock, outcome=DecisionOutcome.REJECTED)

    with pytest.raises(InvalidTransition):
        _decide(reviewer, ready.pk, clock)


# --- approve with edits ----------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_clean_edit_is_approved_as_reviewer_authored_v2(ready: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    v1 = ready.current_version
    assert v1 is not None
    # Same human checklist item, same (absent) quote: its dismissal carries; the rate claim's warning too.
    decision_id = _decide(
        reviewer,
        ready.pk,
        clock,
        outcome=DecisionOutcome.APPROVED_WITH_EDITS,
        edited_content_text=RATE_COPY.replace("Apply online", "Apply"),
    )

    decision = Decision.objects.select_related("version").get(pk=decision_id)
    assert (decision.version.n, decision.version.origin, decision.version.author) == (2, "reviewer_edit", reviewer)
    assert (decision.outcome, decision.ai_review_carried_from) == ("approved_with_edits", v1)
    assert Finding.objects.filter(version=decision.version, carried_from__isnull=False).exists()
    item = ReviewItem.objects.get(pk=ready.pk)
    assert (item.status, item.current_version, item.llm_check_status) == (
        ItemStatus.APPROVED,
        decision.version,
        CheckStatus.SUCCEEDED,
    )


@pytest.mark.django_db
def test_edit_that_raises_findings_keeps_v2_for_triage_then_approves(
    ready: ReviewItem, reviewer: User, clock: FixedClock
) -> None:
    with pytest.raises(FindingsNeedTriage) as caught:
        _decide(
            reviewer,
            ready.pk,
            clock,
            outcome=DecisionOutcome.APPROVED_WITH_EDITS,
            edited_content_text="Guaranteed approval. " + RATE_COPY,
        )

    assert caught.value.details["version_n"] == 2
    findings = caught.value.details["findings"]
    assert isinstance(findings, list)
    assert "claims.guaranteed" in {f["rule_id"] for f in findings if isinstance(f, dict)}
    item = ReviewItem.objects.get(pk=ready.pk)
    assert (item.status, item.current_version.n if item.current_version else None) == (ItemStatus.IN_REVIEW, 2)
    assert not Decision.objects.exists()

    dismiss_all(ready.pk, reviewer, clock, reason="Licensed claim, see memo")
    decision_id = _decide(reviewer, ready.pk, clock, outcome=DecisionOutcome.APPROVED_WITH_EDITS, version_n=2)

    assert Decision.objects.get(pk=decision_id).version.n == 2
    assert ReviewItem.objects.get(pk=ready.pk).status == ItemStatus.APPROVED


@pytest.mark.django_db
def test_edits_need_the_reviewed_version_triaged_first(submit: Submit, reviewer: User, clock: FixedClock) -> None:
    item_id = submit(content_text="Guaranteed approval.").item_id
    ai_done(item_id)

    with pytest.raises(OpenFindingsBlockDecision):
        _decide(reviewer, item_id, clock, outcome=DecisionOutcome.APPROVED_WITH_EDITS, edited_content_text="Fixed.")

    assert Version.objects.filter(item_id=item_id).count() == 1


@pytest.mark.django_db
def test_approve_with_edits_without_text_needs_a_reviewer_version(
    ready: ReviewItem, reviewer: User, clock: FixedClock
) -> None:
    with pytest.raises(InvalidInput) as caught:
        _decide(reviewer, ready.pk, clock, outcome=DecisionOutcome.APPROVED_WITH_EDITS)

    assert caught.value.fields[0].loc == ("body", "edited_content_text")


# --- fast-track lane (workstream F's entry) --------------------------------------------------------------------


@pytest.mark.django_db
def test_fast_track_lane_approves_a_generated_version(
    ready: ReviewItem, reviewer: User, lead: User, clock: FixedClock
) -> None:
    _decide(reviewer, ready.pk, clock)
    ReviewItem.objects.filter(pk=ready.pk).update(
        status=ItemStatus.NEEDS_REREVIEW, reopen_reason=ReopenReason.TERMS_CHANGED
    )
    item = ReviewItem.objects.get(pk=ready.pk)
    base = item.current_version
    from django.db import transaction

    with transaction.atomic():
        generated = create_version(
            item=item, text=RATE_COPY, author=lead, origin=VersionOrigin.FAST_TRACK, based_on=base, clock=clock
        )
    dismiss_all(ready.pk, reviewer, clock)

    decision_id = _decide(reviewer, ready.pk, clock, lane=DecisionLane.FAST_TRACK, version_n=generated.version.n)

    decision = Decision.objects.get(pk=decision_id)
    assert (decision.lane, decision.ai_review_carried_from) == ("fast_track", base)
    item.refresh_from_db()
    assert (item.status, item.reopen_reason) == (ItemStatus.APPROVED, None)


@pytest.mark.django_db
def test_fast_track_lane_refuses_a_submission_version(ready: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    ReviewItem.objects.filter(pk=ready.pk).update(
        status=ItemStatus.NEEDS_REREVIEW, reopen_reason=ReopenReason.TERMS_CHANGED
    )

    with pytest.raises(Conflict, match="generated"):
        _decide(reviewer, ready.pk, clock, lane=DecisionLane.FAST_TRACK)


# --- reaffirm and pull -----------------------------------------------------------------------------------------


@pytest.fixture
def rereview(ready: ReviewItem, reviewer: User, clock: FixedClock) -> ReviewItem:
    _decide(reviewer, ready.pk, clock)
    ReviewItem.objects.filter(pk=ready.pk).update(
        status=ItemStatus.NEEDS_REREVIEW, reopen_reason=ReopenReason.APPROVAL_EXPIRED
    )
    clock.advance(timedelta(days=365))
    return ReviewItem.objects.get(pk=ready.pk)


@pytest.mark.django_db
def test_reaffirm_reapproves_the_same_version_with_a_new_expiry(
    rereview: ReviewItem, reviewer: User, clock: FixedClock
) -> None:
    result = reaffirm(actor=reviewer, item_id=rereview.pk, reason="Still accurate", clock=clock)

    decision = Decision.objects.get(pk=result.decision_id)
    assert (decision.lane, decision.version, decision.expires_at) == (
        "reaffirm",
        rereview.current_version,
        datetime(2028, 10, 24, 15, 0, tzinfo=UTC),
    )
    rereview.refresh_from_db()
    assert (rereview.status, rereview.reopen_reason) == (ItemStatus.APPROVED, None)


@pytest.mark.django_db
def test_reaffirm_rechecks_and_refuses_on_new_findings(rereview: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    # A rule that started firing after the approval: simulated by forgetting one stored finding.
    Finding.objects.filter(version=rereview.current_version, source="human").delete()

    with pytest.raises(FindingsNeedTriage):
        reaffirm(actor=reviewer, item_id=rereview.pk, reason="Still accurate", clock=clock)

    new = Finding.objects.get(version=rereview.current_version, source="human")
    assert new.state == "open"
    assert ReviewItem.objects.get(pk=rereview.pk).open_findings_count == 1
    dismiss_finding(actor=reviewer, finding_id=new.pk, reason="Imagery unchanged", clock=clock)
    reaffirm(actor=reviewer, item_id=rereview.pk, reason="Still accurate", clock=clock)


@pytest.mark.django_db
def test_reaffirm_only_from_needs_rereview(ready: ReviewItem, reviewer: User, clock: FixedClock) -> None:
    with pytest.raises(InvalidTransition):
        reaffirm(actor=reviewer, item_id=ready.pk, reason="x", clock=clock)


def _placement(item: ReviewItem, user: User, **fields: object) -> Placement:
    values: dict[str, object] = {
        "item": item,
        "approved_version": item.current_version,
        "location": "LoanFinder top-of-funnel",
        "first_run": date(2026, 10, 1),
        "created_by": user,
        "created_at": datetime(2026, 10, 1, tzinfo=UTC),
    }
    values.update(fields)
    return Placement.objects.create(**values)


@pytest.mark.django_db
def test_pull_requests_takedown_of_live_placements_and_withdraws(
    rereview: ReviewItem, reviewer: User, marketer: User, clock: FixedClock
) -> None:
    live = _placement(rereview, marketer)
    ended = _placement(rereview, marketer, last_run=date(2026, 10, 5))

    pull_item(actor=reviewer, item_id=rereview.pk, reason="Rates changed", clock=clock)

    live.refresh_from_db()
    ended.refresh_from_db()
    assert (live.takedown_state, live.takedown_requested_at) == (TakedownState.REQUESTED, clock.now())
    assert ended.takedown_state is None
    rereview.refresh_from_db()
    assert (rereview.status, rereview.reopen_reason) == (ItemStatus.WITHDRAWN, None)
    withdrawn = Event.objects.get(type=EventType.ITEM_WITHDRAWN)
    assert withdrawn.payload == {"reason": "Rates changed", "placement_ids": [live.pk]}
    assert Event.objects.get(type=EventType.TAKEDOWN_REQUESTED).entity_id == live.pk


@pytest.mark.django_db
def test_rejecting_live_content_after_rereview_requests_its_takedown(
    rereview: ReviewItem, reviewer: User, marketer: User, clock: FixedClock
) -> None:
    live = _placement(rereview, marketer)
    from reviews.assignment import claim_item

    claim_item(actor=reviewer, item_id=rereview.pk, clock=clock)
    _decide(reviewer, rereview.pk, clock, outcome=DecisionOutcome.REJECTED, reason="Misleading now")

    live.refresh_from_db()
    assert (live.takedown_state, live.takedown_requested_at) == (TakedownState.REQUESTED, clock.now())
    assert Event.objects.get(type=EventType.TAKEDOWN_REQUESTED).payload["reason"] == "Misleading now"


@pytest.mark.django_db
def test_pull_refuses_placements_of_another_item(
    rereview: ReviewItem, ready: ReviewItem, reviewer: User, marketer: User, submit: Submit, clock: FixedClock
) -> None:
    other = ReviewItem.objects.get(pk=submit().item_id)
    foreign = _placement(other, marketer)

    with pytest.raises(InvalidInput):
        pull_item(actor=reviewer, item_id=rereview.pk, reason="x", placement_ids=(foreign.pk,), clock=clock)

    assert ReviewItem.objects.get(pk=rereview.pk).status == ItemStatus.NEEDS_REREVIEW


# --- expiry ----------------------------------------------------------------------------------------------------


def test_add_months_clamps_to_the_month_end() -> None:
    assert add_months(datetime(2026, 1, 31, 9, tzinfo=UTC), 1) == datetime(2026, 2, 28, 9, tzinfo=UTC)
    assert add_months(datetime(2027, 8, 31, tzinfo=UTC), 6) == datetime(2028, 2, 29, tzinfo=UTC)
    assert add_months(datetime(2026, 10, 24, tzinfo=UTC), 12) == datetime(2027, 10, 24, tzinfo=UTC)


@pytest.mark.django_db
def test_send_window_expiry_is_midnight_after_the_last_run() -> None:
    at = datetime(2026, 10, 24, 15, tzinfo=UTC)

    def expiry(first: date | None, last: date | None, channel: Channel = Channel.EMAIL) -> datetime:
        return approval_expiry(
            channel=channel, decided_at=at, planned_first_run=first, planned_last_run=last, today=at.date()
        )

    assert expiry(date(2026, 11, 1), date(2026, 11, 3)) == datetime(2026, 11, 4, tzinfo=UTC)
    assert expiry(date(2026, 11, 1), None) == datetime(2026, 11, 2, tzinfo=UTC)
    assert expiry(date(2026, 9, 1), date(2026, 9, 2)) == datetime(2026, 10, 25, tzinfo=UTC)  # window already over
    assert expiry(None, None, Channel.AFFILIATE_PAGE) == datetime(2027, 4, 24, 15, tzinfo=UTC)
    ExpiryPolicy.objects.filter(channel=Channel.DISPLAY).delete()
    assert expiry(None, None, Channel.DISPLAY) == datetime(2027, 4, 24, 15, tzinfo=UTC)  # fallback: 6 months
