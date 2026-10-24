"""The seeded demo, built once per module through `reset_demo` and committed, then torn down."""

import json
from collections import Counter
from dataclasses import replace
from io import StringIO

import pytest
from django.core.management import call_command

from audit.models import Event, ProcessedEvent
from audit.outbox import REGISTRY
from checks.engine.registry import CODE_RULES
from checks.models import CheckRun, Finding
from core.domain import (
    CheckStatus,
    DecisionLane,
    DriftResult,
    EventType,
    FindingSource,
    FindingState,
    ItemStatus,
    Product,
    ReopenReason,
    VersionOrigin,
)
from demo.content import CATALOG
from demo.reset import reset_demo
from demo.runner import SeedError
from demo.tests.conftest import NOW, Seeded
from drift.compare import compare
from drift.demo import PAGES, is_edited, page_url
from reviews.models import Decision, Placement, ReviewItem, Snapshot, Version
from terms.models import OfferTerms

pytestmark = pytest.mark.django_db


def test_seed_counts_per_status(seeded: Seeded) -> None:
    native = ReviewItem.objects.filter(is_legacy=False)
    counts = Counter(native.values_list("status", flat=True))
    assert seeded.result.items == native.count() == 44
    assert set(counts) == {s.value for s in ItemStatus} - {ItemStatus.DRAFT.value}
    assert counts == {
        ItemStatus.SUBMITTED.value: 5,
        ItemStatus.IN_REVIEW.value: 9,
        ItemStatus.CHANGES_REQUESTED.value: 4,
        ItemStatus.APPROVED.value: 14,
        ItemStatus.REJECTED.value: 3,
        ItemStatus.NEEDS_REREVIEW.value: 4,
        ItemStatus.EXPIRED.value: 3,
        ItemStatus.WITHDRAWN.value: 2,
    }
    reasons = Counter(native.filter(status=ItemStatus.NEEDS_REREVIEW.value).values_list("reopen_reason", flat=True))
    assert reasons == {
        ReopenReason.TERMS_CHANGED.value: 2,
        ReopenReason.APPROVAL_EXPIRED.value: 1,
        ReopenReason.DRIFT_DETECTED.value: 1,
    }


def test_every_native_item_has_its_history_in_events(seeded: Seeded) -> None:
    for item in ReviewItem.objects.filter(is_legacy=False):
        types = set(Event.objects.filter(item=item).values_list("type", flat=True))
        assert {
            EventType.ITEM_SUBMITTED.value,
            EventType.ITEM_ASSIGNED.value,
            EventType.CHECKS_COMPLETED.value,
        } <= types
    assert Event.objects.filter(type=EventType.DEMO_RESET.value).count() == 1


def test_every_code_rule_fires_on_a_persisted_version(seeded: Seeded) -> None:
    fired = set(Finding.objects.filter(source=FindingSource.CODE.value).values_list("rule_id", flat=True))
    assert {r.spec.id for r in CODE_RULES} - fired == set()


def test_findings_are_triaged_like_a_team_would(seeded: Seeded) -> None:
    states = Counter(Finding.objects.values_list("state", flat=True))
    assert states[FindingState.ACCEPTED.value] >= 40
    assert states[FindingState.DISMISSED.value] >= 40
    assert Finding.objects.filter(state=FindingState.DISMISSED.value, carried_from__isnull=False).exists()
    assert Finding.objects.filter(state=FindingState.DISMISSED.value, resolved_by__isnull=True).exists()  # system


def test_ai_results_are_persisted_and_scripted(seeded: Seeded) -> None:
    runs = CheckRun.objects.filter(source=FindingSource.LLM.value)
    assert set(runs.exclude(status=CheckStatus.SUCCEEDED.value).values_list("status", flat=True)) == {
        CheckStatus.FAILED.value,
        CheckStatus.PENDING.value,
    }
    assert set(runs.filter(status=CheckStatus.SUCCEEDED.value).values_list("model", flat=True)) == {"demo-seed"}
    assert Finding.objects.filter(source=FindingSource.LLM.value).count() >= 10
    native = ReviewItem.objects.filter(is_legacy=False)
    assert native.filter(llm_check_status=CheckStatus.FAILED.value).count() == 1
    assert native.filter(llm_check_status=CheckStatus.PENDING.value).count() == 1


def test_legacy_import_matches_the_tracker_readme(seeded: Seeded) -> None:
    assert seeded.result.legacy_items == 178
    legacy = ReviewItem.objects.filter(is_legacy=True)
    assert legacy.filter(partner__isnull=False).count() == 33  # joined to the seeded partners, not duplicates
    assert Event.objects.filter(type=EventType.ITEM_IMPORTED.value).count() == 178


def test_offer_terms_history_and_fast_track(seeded: Seeded) -> None:
    assert list(
        OfferTerms.objects.filter(product=Product.PERSONAL_LOAN).order_by("version").values_list("version")
    ) == [
        (1,),
        (2,),
        (3,),
    ]
    assert OfferTerms.objects.filter(product=Product.CREDIT_CARD).count() == 2
    assert Version.objects.filter(origin=VersionOrigin.FAST_TRACK.value).count() >= 8
    assert Decision.objects.filter(lane=DecisionLane.FAST_TRACK.value).count() == 5
    assert Decision.objects.filter(lane=DecisionLane.REAFFIRM.value).count() == 1


def test_every_seeded_event_was_delivered_in_process(seeded: Seeded) -> None:
    for spec in REGISTRY.all():
        expected = set(Event.objects.filter(type__in=[t.value for t in spec.event_types]).values_list("pk", flat=True))
        delivered = set(ProcessedEvent.objects.filter(handler=spec.name).values_list("event_id", flat=True))
        assert expected == delivered, spec.name


def test_the_seed_starts_no_background_work(seeded: Seeded) -> None:
    """No seeded version gets a live AI call, and the fan-out and import were done in-process, not enqueued."""
    assert seeded.enqueued == []


def test_a_failing_reset_changes_nothing(seeded: Seeded) -> None:
    before = (_state(), _pages())
    story = CATALOG.stories[0]
    broken = replace(CATALOG, stories=(replace(story, expect=ItemStatus.REJECTED),))
    with pytest.raises(SeedError, match=story.key):
        reset_demo(now=NOW, catalog=broken)
    assert (_state(), _pages()) == before


def test_the_hosted_demo_pages_carry_the_approved_copy(seeded: Seeded) -> None:
    """Each demo partner page has a seeded item approved with the page's copy, live there and monitored, so a check
    run after the seed finds what the seeded checks found."""
    for page in PAGES:
        item = ReviewItem.objects.get(title=page.item_title)
        placement = Placement.objects.get(item=item, url=page_url(page.slug))
        assert placement.monitored
        latest = Snapshot.objects.filter(placement=placement).order_by("-pk").first()
        assert latest is not None, page.slug
        assert latest.compared_version is not None
        assert compare(latest.compared_version.content_text, page.copy).result is DriftResult.UNCHANGED, page.slug
    assert _pages() == {"lendcompare": True, "cardscout": False, "budgetbee": False}


def test_the_drift_rereview_comes_from_a_real_check(seeded: Seeded) -> None:
    item = ReviewItem.objects.get(title="LendCompare: best debt consolidation loans listing")
    modified = Snapshot.objects.get(placement__item=item, result=DriftResult.MODIFIED.value)
    # The rate sheet reopened it first (terms changed, then fast-tracked); the partner's edit reopened it again.
    reopens = list(Event.objects.filter(item_id=item.pk, type=EventType.ITEM_REOPENED.value).order_by("pk"))
    reopened = reopens[-1]

    assert (item.status, item.reopen_reason) == (ItemStatus.NEEDS_REREVIEW.value, ReopenReason.DRIFT_DETECTED.value)
    assert [e.payload["reason"] for e in reopens] == [
        ReopenReason.TERMS_CHANGED.value,
        ReopenReason.DRIFT_DETECTED.value,
    ]
    assert reopened.payload["snapshot_id"] == modified.pk
    assert "7.99" in json.dumps(modified.diff)


# docs/demo.md walks evaluators through these items by key.
GUIDE_KEYS: dict[int, str] = {
    2: "PL debt consolidation landing page",
    7: "LendCompare: best debt consolidation loans listing",
    8: "Display banner: one payment, one plan",
    10: "Paid social: consolidate and breathe",
    11: "Prescreened firm-offer letter, fall drop",
    13: "Paid social video: one payment, 15s",
    22: "Paid social: no fees, no surprises",
    23: "CardScout: ClearPath Card review",
    26: "Money with Maya: card payoff reel",
    31: "Card prescreen mailer: pre-selected offer",
    32: "BudgetBee: debt consolidation article",
    35: "Email: fund your home project",
    37: "Direct mail: homeowners refi postcard",
    38: "Golden State Saver newsletter: card spotlight",
    40: "FinMatch: prequal marketplace listing",
    222: "Display banner: get ahead of holiday bills",
}


def test_the_keys_the_guide_cites_are_the_items_it_describes(seeded: Seeded) -> None:
    titles = dict(ReviewItem.objects.filter(pk__in=GUIDE_KEYS).values_list("pk", "title"))
    assert titles == GUIDE_KEYS


def test_seed_demo_without_reset_leaves_existing_data_alone(seeded: Seeded) -> None:
    before = _state()
    out = StringIO()
    call_command("seed_demo", stdout=out)
    assert "nothing seeded" in out.getvalue()
    assert _state() == before


def test_reset_restores_the_same_state(seeded: Seeded, snapshot: dict[str, tuple[int, str]]) -> None:
    ReviewItem.objects.filter(title="Display banner: one payment, one plan").update(notes="scribbled on by a visitor")
    reset_demo(now=NOW)
    assert _state() == snapshot


def _pages() -> dict[str, bool]:
    return {page.slug: is_edited(page.slug) for page in PAGES}


def _state() -> dict[str, tuple[int, str]]:
    return {title: (pk, status) for pk, title, status in ReviewItem.objects.values_list("pk", "title", "status")}


@pytest.fixture
def snapshot(seeded: Seeded) -> dict[str, tuple[int, str]]:
    return _state()
