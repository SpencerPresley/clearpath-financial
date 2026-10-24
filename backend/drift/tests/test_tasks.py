"""The Celery boundary: fetch, then complete or fail; retries for scheduled checks; nothing silent."""

import pytest

from core.clock import FixedClock
from core.domain import CheckStatus, DriftResult, DriftTrigger, ItemStatus
from drift import services, tasks
from drift.fetcher import FetchedPage, FetchError, FetchFailure
from drift.tests.conftest import page_with
from reviews.models import Placement, ReviewItem, Snapshot
from reviews.tests.conftest import CLEAN_COPY

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch, clock: FixedClock) -> None:
    monkeypatch.setattr(tasks, "clock", clock)


def fetches(monkeypatch: pytest.MonkeyPatch, *results: FetchedPage | FetchError) -> list[str]:
    urls: list[str] = []
    queue = list(results)

    def fake(url: str) -> FetchedPage:
        urls.append(url)
        result = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(result, FetchError):
            raise result
        return result

    monkeypatch.setattr(tasks, "fetch", fake)
    return urls


def request(placement: Placement, clock: FixedClock, trigger: DriftTrigger = DriftTrigger.SCHEDULED) -> int:
    return services.request_check(actor=None, placement_id=placement.pk, trigger=trigger, clock=clock)


def test_run_check_fetches_the_placement_url_and_records_the_result(
    placement: Placement, clock: FixedClock, monkeypatch: pytest.MonkeyPatch, enqueued: list[int]
) -> None:
    urls = fetches(monkeypatch, page_with(CLEAN_COPY.replace("minutes", "seconds")))
    snapshot_id = request(placement, clock)

    assert tasks.run_check.apply(args=(snapshot_id,)).get() == "modified reopened"

    assert urls == [placement.url]
    assert Snapshot.objects.get(pk=snapshot_id).result == DriftResult.MODIFIED
    assert ReviewItem.objects.get(pk=placement.item_id).status == ItemStatus.NEEDS_REREVIEW  # pyrefly: ignore[missing-attribute]


def test_a_duplicate_delivery_does_nothing(
    placement: Placement, clock: FixedClock, monkeypatch: pytest.MonkeyPatch, enqueued: list[int]
) -> None:
    urls = fetches(monkeypatch, page_with())
    snapshot_id = request(placement, clock)
    tasks.run_check.apply(args=(snapshot_id,))

    assert tasks.run_check.apply(args=(snapshot_id,)).get() == "noop"
    assert len(urls) == 1


def test_scheduled_check_retries_a_transient_failure_then_succeeds(
    placement: Placement, clock: FixedClock, monkeypatch: pytest.MonkeyPatch, enqueued: list[int]
) -> None:
    urls = fetches(monkeypatch, FetchError(FetchFailure.TIMEOUT), page_with())
    snapshot_id = request(placement, clock)

    tasks.run_check.apply(args=(snapshot_id,))

    snapshot = Snapshot.objects.get(pk=snapshot_id)
    assert (snapshot.status, snapshot.result, snapshot.attempts) == (CheckStatus.SUCCEEDED, DriftResult.UNCHANGED, 2)
    assert len(urls) == 2


def test_scheduled_check_gives_up_after_the_budget(
    placement: Placement, clock: FixedClock, monkeypatch: pytest.MonkeyPatch, enqueued: list[int]
) -> None:
    urls = fetches(monkeypatch, FetchError(FetchFailure.CONNECT_FAILED))
    snapshot_id = request(placement, clock)

    tasks.run_check.apply(args=(snapshot_id,))

    snapshot = Snapshot.objects.get(pk=snapshot_id)
    assert (snapshot.status, snapshot.error_code, snapshot.attempts) == (
        CheckStatus.FAILED,
        "connect_failed",
        services.MAX_SCHEDULED_ATTEMPTS,
    )
    assert len(urls) == services.MAX_SCHEDULED_ATTEMPTS


def test_manual_check_fails_after_one_attempt(
    placement: Placement, clock: FixedClock, monkeypatch: pytest.MonkeyPatch, enqueued: list[int]
) -> None:
    urls = fetches(monkeypatch, FetchError(FetchFailure.TIMEOUT))
    snapshot_id = request(placement, clock, DriftTrigger.MANUAL)

    assert tasks.run_check.apply(args=(snapshot_id,)).get() == "failed timeout"
    assert len(urls) == 1
    assert Snapshot.objects.get(pk=snapshot_id).status == CheckStatus.FAILED


def test_an_unexpected_error_becomes_visible_state(
    placement: Placement, clock: FixedClock, monkeypatch: pytest.MonkeyPatch, enqueued: list[int]
) -> None:
    def boom(url: str) -> FetchedPage:
        raise RuntimeError("bug")

    monkeypatch.setattr(tasks, "fetch", boom)
    snapshot_id = request(placement, clock)

    tasks.run_check.apply(args=(snapshot_id,))

    snapshot = Snapshot.objects.get(pk=snapshot_id)
    assert (snapshot.status, snapshot.error_code) == (CheckStatus.FAILED, "error")


def test_sweep_task_requests_and_enqueues(
    placement: Placement, enqueued: list[int], django_capture_on_commit_callbacks
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        assert tasks.sweep.apply().get() == 1
    assert enqueued == [Snapshot.objects.get(placement=placement).pk]


def test_fetch_seam_goes_through_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real seam refuses a metadata address before any network I/O.
    with pytest.raises(FetchError) as caught:
        tasks.fetch("http://169.254.169.254/latest/meta-data/")
    assert caught.value.code is FetchFailure.ADDRESS_NOT_ALLOWED
