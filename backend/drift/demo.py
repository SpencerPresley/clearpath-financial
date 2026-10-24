"""Demo affiliate pages for the drift monitor (product-spec "Drift monitoring": "2-3 affiliate pages we host
ourselves, with a 'simulate edit' button"). Demo-only: nothing here is a real partner.

Each page carries the approved copy of one demo item. The demo seed creates that item (approved, with the page's
`copy`) and calls `seed_placement` to record a monitored placement on the page.
"Simulate edit" flips a page to its edited variant. The flag lives in the shared cache (Redis in dev and prod) so the
web process that serves the page and the worker that fetches it agree, with no model of its own; a cache flush
returns every page to its original, which is also what `reset_demo_pages` does for the admin "Reset demo".

The pages are served at `<DEMO_PARTNERS_BASE_URL>/demo-partners/<slug>/`, the public site in production (CloudFront
routes `/demo-partners/*` to the app), so the drift check fetches them through the same SSRF guard as any partner.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Final

from django.conf import settings
from django.core.cache import cache
from django.template.loader import render_to_string

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import Product, Role
from core.errors import NotFound
from core.permissions import require_role
from reviews.placements import PlacementInput, record_placement

PATH_PREFIX: Final = "/demo-partners/"
_KEY: Final = "drift:demo:{slug}:edited"


@dataclass(frozen=True)
class DemoPage:
    slug: str
    partner: str  # the demo partner's name
    title: str  # <title>
    headline: str
    item_title: str
    product: Product
    copy: str  # the approved copy, as the partner first published it
    edited_copy: str | None  # what "Simulate edit" publishes instead; None removes the offer from the page
    edited_headline: str  # page noise that changes with the edit as well
    edit_summary: str  # what the edit does, in the reviewer's words
    expected: str  # the drift result the edit should produce


# The demo pages carry the seeded world's offer (docs/demo.md): ClearPath Card issued by Harborview Bank, N.A.;
# personal-loan APRs from today's offer terms. The demo seed's items for these pages are approved with exactly
# `copy`, so the first check of each comes back unchanged.
_LENDCOMPARE: Final = (
    "Advertiser Disclosure: LendCompare receives compensation from the lenders listed on this page, which may affect "
    "where and how they appear.\n\n"
    "Best Debt Consolidation Loans This Year\n\n"
    "ClearPath Financial: Editor's Pick\n"
    "Fixed APRs from 9.99% to 35.99%. Your rate depends on your credit history, income and other factors; the lowest "
    "rates go to the most creditworthy applicants. Loans from $1,000 to $50,000. Subject to credit approval.\n\n"
    "Why we like it: fast funding, no prepayment penalty, and a simple online application.\n\n"
    "See my rates"
)
_BUDGETBEE: Final = (
    "Sponsored by ClearPath. BudgetBee earns a fee if you apply.\n\n"
    "Consolidate high-interest debt with a ClearPath personal loan. Fixed APRs from 9.99% to 35.99%. Your rate "
    "depends on your credit history, income and other factors; the lowest rates go to the most creditworthy "
    "applicants. Borrow $1,000 to $50,000 with no prepayment penalty. Subject to credit approval.\n\n"
    "Loans made or arranged pursuant to a California Financing Law license, #60DBO-184027."
)

PAGES: Final = (
    DemoPage(
        slug="lendcompare",
        partner="LendCompare",
        title="Best debt consolidation loans of 2026 | LendCompare",
        headline="Debt consolidation loans: our top picks",
        item_title="LendCompare: best debt consolidation loans listing",
        product=Product.PERSONAL_LOAN,
        copy=_LENDCOMPARE,
        edited_copy=_LENDCOMPARE.replace("from 9.99%", "from 7.99%").replace(
            "Subject to credit approval.", "Guaranteed approval for most applicants."
        ),
        edited_headline="Top debt consolidation loans this week",
        edit_summary=(
            "The partner lowers the starting APR to 7.99% and swaps 'Subject to credit approval' for 'Guaranteed "
            "approval for most applicants.'"
        ),
        expected="modified",
    ),
    DemoPage(
        slug="cardscout",
        partner="CardScout",
        title="ClearPath Card review | CardScout",
        headline="ClearPath Card review: a no-annual-fee card",
        item_title="CardScout: ClearPath Card review",
        product=Product.CREDIT_CARD,
        copy=(
            "Advertiser disclosure: CardScout receives compensation from ClearPath for this listing.\n\n"
            "The ClearPath Card: 0% intro APR on purchases for 15 months from account opening, then a variable APR "
            "of 24.74% to 33.74% based on your creditworthiness. $0 annual fee. Balance transfer fee: 3% of each "
            "transfer (min $5).\n\n"
            "The ClearPath Card is issued by Harborview Bank, N.A., Member FDIC, pursuant to a license from Visa."
        ),
        edited_copy=None,
        edited_headline="Our favorite cards this month",
        edit_summary="The partner takes the ClearPath offer off the page and features other cards.",
        expected="missing",
    ),
    DemoPage(
        slug="budgetbee",
        partner="BudgetBee",
        title="How to consolidate credit card debt | BudgetBee",
        headline="How to consolidate credit card debt",
        item_title="BudgetBee: debt consolidation article",
        product=Product.PERSONAL_LOAN,
        copy=_BUDGETBEE,
        # Same words, new layout: every sentence on its own line.
        edited_copy=_BUDGETBEE.replace(". ", ".\n"),
        edited_headline="Debt consolidation: a step-by-step guide (updated)",
        edit_summary=(
            "The partner redesigns the article (new headline, layout and sidebar) but keeps the approved copy word "
            "for word."
        ),
        expected="unchanged",
    ),
)
_BY_SLUG: Final = {p.slug: p for p in PAGES}


def get_page(slug: str) -> DemoPage | None:
    return _BY_SLUG.get(slug)


def base_url() -> str:
    return str(settings.DEMO_PARTNERS_BASE_URL).rstrip("/")


def page_url(slug: str) -> str:
    return f"{base_url()}{PATH_PREFIX}{slug}/"


def slug_for_url(url: str) -> str | None:
    """The demo page a placement URL points at, if any (only on this deployment's demo base URL)."""
    prefix = f"{base_url()}{PATH_PREFIX}"
    if not url.startswith(prefix):
        return None
    slug = url[len(prefix) :].split("/", 1)[0].split("?", 1)[0]
    return slug if slug in _BY_SLUG else None


def render_page(page: DemoPage, *, edited: bool, today: date) -> str:
    """The page's HTML as `/demo-partners/<slug>/` serves it. The demo seed renders the same HTML to record the
    checks a fetch would have made, without a web server to fetch from."""
    # Page noise that changes every day, like a real partner page: the date and a reader count.
    reads = 1000 + int(hashlib.sha256(f"{page.slug}{today}".encode()).hexdigest()[:4], 16) % 9000
    context = {
        "page": page,
        "edited": edited,
        "copy": page.edited_copy if edited else page.copy,
        "today": today,
        "reads": f"{reads:,}",
    }
    return render_to_string("drift/partner_page.html", context)


def is_edited(slug: str) -> bool:
    return bool(cache.get(_KEY.format(slug=slug), default=False))


def set_edited(*, actor: User, slug: str, edited: bool) -> DemoPage:
    """Lead or admin: publish the page's edited variant (or put the original back). Demo state, not domain state,
    so no event; the drift check that follows records what it found."""
    require_role(actor, Role.LEAD, Role.ADMIN)
    page = get_page(slug)
    if page is None:
        raise NotFound.entity("demo page", slug)
    cache.set(_KEY.format(slug=slug), edited, timeout=None)
    return page


def seed_placement(*, actor: User, item_id: int, slug: str, clock: Clock = SYSTEM_CLOCK) -> int:
    """For the demo seed (workstream L): record a monitored, open-ended placement of an approved item on a demo
    page, from today. The item's approved copy should be the page's `copy` so the first check comes back unchanged."""
    page = get_page(slug)
    if page is None:
        raise NotFound.entity("demo page", slug)
    data = PlacementInput(
        location=f"{page.partner}: {page.headline}", url=page_url(slug), first_run=clock.today(), monitored=True
    )
    return record_placement(actor=actor, item_id=item_id, data=data, clock=clock)


def reset_demo_pages(*, edited: frozenset[str] = frozenset()) -> None:
    """Every demo page back to its original, except the `edited` ones (for the admin "Reset demo": the seed can
    start a page edited so a drift re-review exists out of the box)."""
    cache.delete_many([_KEY.format(slug=p.slug) for p in PAGES if p.slug not in edited])
    for slug in edited:
        if slug not in _BY_SLUG:
            raise NotFound.entity("demo page", slug)
        cache.set(_KEY.format(slug=slug), value=True, timeout=None)
