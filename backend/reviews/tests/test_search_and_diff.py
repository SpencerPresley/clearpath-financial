import pytest

from accounts.models import User
from core.clock import FixedClock
from core.domain import DecisionLane, DecisionOutcome, ItemStatus, Product
from reviews.diff import DiffOp, DiffSegment, diff_texts
from reviews.filters import ItemFilter
from reviews.models import Decision
from reviews.search import find_phrase, search_text
from reviews.tests.factories import AT, make_item, make_version


def test_diff_texts_is_word_level() -> None:
    segments = diff_texts("Rates from 7.49% APR.", "Rates from 6.99% APR for you.")

    assert segments == (
        DiffSegment(DiffOp.EQUAL, "Rates from "),
        DiffSegment(DiffOp.DELETE, "7.49"),
        DiffSegment(DiffOp.INSERT, "6.99"),
        DiffSegment(DiffOp.EQUAL, "% APR"),
        DiffSegment(DiffOp.INSERT, " for you"),
        DiffSegment(DiffOp.EQUAL, "."),
    )


def test_diff_of_identical_texts_is_one_equal_segment() -> None:
    assert diff_texts("same", "same") == (DiffSegment(DiffOp.EQUAL, "same"),)


def test_diff_reassembles_both_sides() -> None:
    old, new = "No annual fee. Intro 0% APR for 15 months.", "No annual fee! Intro 0% APR for 18 months, then 21.99%."
    segments = diff_texts(old, new)

    assert "".join(s.text for s in segments if s.op is not DiffOp.INSERT) == old
    assert "".join(s.text for s in segments if s.op is not DiffOp.DELETE) == new


@pytest.mark.django_db
def test_find_phrase_matches_case_insensitively_and_returns_latest_decision(
    marketer: User, reviewer: User, clock: FixedClock
) -> None:
    approved = make_item(marketer, title="Soft pull page", status=ItemStatus.APPROVED)
    version = make_version(approved, "Checking your rate WON'T AFFECT YOUR CREDIT SCORE.")
    Decision.objects.create(
        item=approved,
        version=version,
        outcome=DecisionOutcome.APPROVED,
        lane=DecisionLane.STANDARD,
        approver=reviewer,
        reason="Limited to the soft-pull step.",
        ruleset_date=AT.date(),
        expires_at=AT,
        decided_at=AT,
    )
    other = make_item(marketer, title="Unrelated")
    make_version(other, "Low rates for everyone.")

    hits = find_phrase(viewer=reviewer, phrase="won't affect your credit score", filters=ItemFilter(), clock=clock)

    assert [h.item_id for h in hits] == [approved.pk]
    hit = hits[0]
    assert (hit.version_n, hit.version_outcome, hit.key) == (1, DecisionOutcome.APPROVED, f"CP-{approved.pk}")
    assert [p.text for p in hit.snippet if p.highlighted] == ["WON'T AFFECT YOUR CREDIT SCORE"]
    assert "".join(p.text for p in hit.snippet) == "Checking your rate WON'T AFFECT YOUR CREDIT SCORE."


def _decide(item_version: tuple, reviewer: User, outcome: DecisionOutcome, hour: int) -> None:
    item, version = item_version
    Decision.objects.create(
        item=item,
        version=version,
        outcome=outcome,
        lane=DecisionLane.STANDARD,
        approver=reviewer,
        reason="Decided.",
        ruleset_date=AT.date(),
        expires_at=AT,
        decided_at=AT.replace(hour=hour),
    )


@pytest.mark.django_db
def test_hit_outcome_is_the_matched_versions_decision_not_the_items_latest(
    marketer: User, reviewer: User, clock: FixedClock
) -> None:
    # "Was this phrase approved before?" is a question about the version that contains it.
    item = make_item(marketer, status=ItemStatus.REJECTED)
    v1 = make_version(item, "No hard credit pull to check your rate.", n=1)
    v2 = make_version(item, "Guaranteed approval for everyone.", n=2)
    _decide((item, v1), reviewer, DecisionOutcome.APPROVED, hour=9)
    _decide((item, v2), reviewer, DecisionOutcome.REJECTED, hour=10)

    hits = find_phrase(viewer=reviewer, phrase="no hard credit pull", filters=ItemFilter(), clock=clock)

    assert [(h.version_n, h.version_outcome) for h in hits] == [(1, DecisionOutcome.APPROVED)]
    assert hits[0].version_decided_at == AT.replace(hour=9)


@pytest.mark.django_db
def test_search_text_uses_websearch_syntax_and_ranks(marketer: User, reviewer: User, clock: FixedClock) -> None:
    strong = make_item(marketer, title="Strong")
    _approved(strong, make_version(strong, "No credit check. Credit check free. Checking credit is soft."), reviewer)
    weak = make_item(marketer, title="Weak")
    _approved(weak, make_version(weak, "A credit card with a long check-out flow."), reviewer)
    excluded = make_item(marketer, title="Excluded")
    _approved(excluded, make_version(excluded, "No credit check, guaranteed approval."), reviewer)

    hits = search_text(viewer=reviewer, query='"credit check" -guaranteed', filters=ItemFilter(), clock=clock)

    assert [h.item_id for h in hits] == [strong.pk]
    highlighted = [p.text.lower() for p in hits[0].snippet if p.highlighted]
    assert "credit" in highlighted
    assert "<" not in "".join(p.text for p in hits[0].snippet)


@pytest.mark.django_db
def test_search_respects_item_filter_and_dedupes_by_item(marketer: User, reviewer: User, clock: FixedClock) -> None:
    card = make_item(marketer, product=Product.CREDIT_CARD)
    _approved(card, make_version(card, "No annual fee.", n=1), reviewer)
    _approved(card, make_version(card, "No annual fee, ever.", n=2), reviewer)
    loan = make_item(marketer, product=Product.PERSONAL_LOAN)
    _approved(loan, make_version(loan, "No annual fee on loans."), reviewer)

    hits = search_text(
        viewer=reviewer, query="annual fee", filters=ItemFilter(product=[Product.CREDIT_CARD]), clock=clock
    )

    assert [(h.item_id, h.version_n) for h in hits] == [(card.pk, 2)]


def _approved(item: object, version: object, reviewer: User) -> None:
    _decide((item, version), reviewer, DecisionOutcome.APPROVED, hour=9)


@pytest.mark.django_db
def test_precedent_is_ever_approved_wording_with_its_current_status(
    marketer: User, reviewer: User, clock: FixedClock
) -> None:
    lapsed = make_item(marketer, status=ItemStatus.EXPIRED, reopen_reason="approval_expired")
    _approved(lapsed, make_version(lapsed, "Check your rate with no hard credit pull."), reviewer)
    pending = make_item(marketer, status=ItemStatus.IN_REVIEW)
    make_version(pending, "Check your rate with no hard credit pull today.")
    reworded = make_item(marketer, status=ItemStatus.SUBMITTED)
    _approved(reworded, make_version(reworded, "No hard credit pull to check.", n=1), reviewer)
    make_version(reworded, "No hard credit pull to check, ever.", n=2)

    for hits in (
        find_phrase(viewer=reviewer, phrase="no hard credit pull", filters=ItemFilter(), clock=clock),
        search_text(viewer=reviewer, query="hard credit pull", filters=ItemFilter(), clock=clock),
    ):
        assert sorted((h.item_id, h.version_n, h.status) for h in hits) == [
            (lapsed.pk, 1, ItemStatus.EXPIRED),
            (reworded.pk, 1, ItemStatus.SUBMITTED),
        ]
