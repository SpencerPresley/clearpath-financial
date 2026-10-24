"""The fan-out against concurrent work on the same lock (E's lock order: item row, then the assignment advisory lock).

Each test runs real transactions on two threads. T1 is the fan-out over items [A, B], paused inside item A's
transaction after A's re-review took the advisory lock. T2 then does something that takes a row lock and waits on
the advisory lock. With one transaction per item, T1 commits A (releasing the advisory lock) before it touches B,
so both finish. The control runs the same fan-out in one transaction: T1 holds the advisory lock and waits on B's
row, T2 holds B's row and waits on the advisory lock, and Postgres aborts one of them as a deadlock.
"""

import threading
from collections.abc import Callable
from contextlib import nullcontext
from datetime import timedelta

import pytest
from django.db import OperationalError, connection, transaction

from accounts.models import User
from core.clock import FixedClock
from core.domain import ItemStatus, ReopenReason
from reviews.assignment import claim_item
from reviews.models import ReviewItem
from reviews.rereview import _expire_if_due  # the sweep's per-item step
from reviews.services import SubmitItemResult
from reviews.tests.test_assignment import _wait_for_a_blocked_lock
from terms import fanout
from terms.fanout import FanOutOutcome, fan_out_item
from terms.models import OfferTerms
from terms.tests.conftest import WORKED_EXAMPLE, approve, go_live, publish

type Submit = Callable[..., SubmitItemResult]


class _Pause:
    """Make T1's re-review of `item_id` wait, inside its transaction, until released."""

    def __init__(self, item_id: int, monkeypatch: pytest.MonkeyPatch) -> None:
        self.item_id = item_id
        self.reached = threading.Event()
        self.release = threading.Event()
        real = fanout.send_back

        def paused(**kwargs: object) -> int:
            event_id = real(**kwargs)  # pyrefly: ignore[bad-argument-type]
            if kwargs["item_id"] == self.item_id:
                self.reached.set()
                self.release.wait(timeout=15)
            return event_id

        monkeypatch.setattr(fanout, "send_back", paused)


def _live_approval(submit: Submit, reviewer: User, marketer: User, clock: FixedClock) -> ReviewItem:
    item_id = submit(content_text=WORKED_EXAMPLE).item_id
    approve(item_id, reviewer, clock)
    item = ReviewItem.objects.get(pk=item_id)
    go_live(item, marketer, clock)
    return item


def _run(target: Callable[[], object], results: dict[str, object], key: str) -> threading.Thread:
    def body() -> None:
        try:
            results[key] = target()
        except Exception as exc:  # noqa: BLE001  # the test inspects what each thread raised
            results[key] = exc
        finally:
            connection.close()

    thread = threading.Thread(target=body)
    thread.start()
    return thread


def _fan_out_over(item_ids: list[int], clock: FixedClock, *, one_transaction: bool) -> Callable[[], list[object]]:
    def run() -> list[object]:
        with transaction.atomic() if one_transaction else nullcontext():
            return [fan_out_item(item_id=i, clock=clock) for i in item_ids]

    return run


@pytest.fixture
def items(
    pl_terms: OfferTerms, submit: Submit, reviewer: User, marketer: User, lead: User, clock: FixedClock
) -> tuple[ReviewItem, ReviewItem]:
    a = _live_approval(submit, reviewer, marketer, clock)
    b = _live_approval(submit, reviewer, marketer, clock)
    publish(lead, clock)
    return a, b


@pytest.mark.django_db(transaction=True)
def test_fan_out_does_not_deadlock_against_a_concurrent_claim(
    items: tuple[ReviewItem, ReviewItem],
    submit: Submit,
    lead: User,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a, b = items
    claimed = ReviewItem.objects.get(pk=submit().item_id)  # assigned to the reviewer; the lead claims it
    pause = _Pause(a.pk, monkeypatch)
    results: dict[str, object] = {}

    t1 = _run(_fan_out_over([a.pk, b.pk], clock, one_transaction=False), results, "fan_out")
    assert pause.reached.wait(timeout=10)
    t2 = _run(lambda: claim_item(actor=lead, item_id=claimed.pk, clock=clock), results, "claim")
    _wait_for_a_blocked_lock("advisory")  # the claim waits for A's re-review to commit
    pause.release.set()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert results["fan_out"] == [FanOutOutcome.REOPENED_FAST_TRACK, FanOutOutcome.REOPENED_FAST_TRACK]
    assert results["claim"] is None
    statuses = dict(ReviewItem.objects.filter(pk__in=[a.pk, b.pk, claimed.pk]).values_list("pk", "status"))
    assert statuses == {a.pk: "needs_rereview", b.pk: "needs_rereview", claimed.pk: "in_review"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("one_transaction", [False, True], ids=["per-item", "one-transaction-control"])
def test_per_item_transactions_avoid_deadlock_with_the_expiry_sweep(
    items: tuple[ReviewItem, ReviewItem],
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    one_transaction: bool,
) -> None:
    a, b = items
    ReviewItem.objects.filter(pk=b.pk).update(approval_expires_at=clock.now() - timedelta(minutes=1))
    pause = _Pause(a.pk, monkeypatch)
    results: dict[str, object] = {}

    t1 = _run(_fan_out_over([a.pk, b.pk], clock, one_transaction=one_transaction), results, "fan_out")
    assert pause.reached.wait(timeout=10)
    t2 = _run(lambda: _expire_if_due(b.pk, clock), results, "sweep")  # locks B's row, then waits on advisory
    _wait_for_a_blocked_lock("advisory")
    pause.release.set()
    t1.join(timeout=15)
    t2.join(timeout=15)

    if one_transaction:
        deadlocked = [r for r in results.values() if isinstance(r, OperationalError)]
        assert len(deadlocked) == 1
        assert "deadlock detected" in str(deadlocked[0])
        return
    # B: the sweep re-reviewed it for expiry first; the fan-out then gave it a generated version.
    assert results == {"fan_out": [FanOutOutcome.REOPENED_FAST_TRACK, FanOutOutcome.REGENERATED], "sweep": True}
    b.refresh_from_db()
    assert (b.status, b.reopen_reason) == (ItemStatus.NEEDS_REREVIEW, ReopenReason.APPROVAL_EXPIRED)
