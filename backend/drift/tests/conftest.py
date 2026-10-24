"""Drift fixtures: an approved item with a monitored live placement, driven through the real services, and a
recorder in place of the Celery enqueue."""

from collections.abc import Callable

import pytest

from accounts.models import User
from core.clock import FixedClock
from drift import services
from drift.fetcher import FetchedPage
from reviews.models import Placement, ReviewItem
from reviews.placements import PlacementInput, record_placement
from reviews.tests.conftest import CLEAN_COPY, approve, approved, pl_terms, submit  # noqa: F401  # fixtures

PAGE_URL = "https://partner.example/best-loans"


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Snapshot ids the services asked Celery to run (on commit)."""
    seen: list[int] = []
    monkeypatch.setattr(services, "enqueue", seen.append)
    return seen


@pytest.fixture
def placement(approved: ReviewItem, marketer: User, clock: FixedClock) -> Placement:  # noqa: F811
    placement_id = record_placement(
        actor=marketer,
        item_id=approved.pk,
        data=PlacementInput(location="LendCompare: best loans", url=PAGE_URL, first_run=clock.today(), monitored=True),
        clock=clock,
    )
    return Placement.objects.get(pk=placement_id)


def page(body: str, *, content_type: str = "text/html") -> FetchedPage:
    return FetchedPage(url=PAGE_URL, final_url=PAGE_URL, status=200, content_type=content_type, text=body)


def page_with(copy: str = CLEAN_COPY) -> FetchedPage:
    return page(
        "<html><head><title>Best loans</title></head><body><nav>Home</nav><p>Updated today</p>"
        f"<div class='offer'><p>{copy}</p></div><footer>Advertiser disclosure</footer></body></html>"
    )


type PageFactory = Callable[..., FetchedPage]
