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

from dataclasses import dataclass
from typing import Final

from django.conf import settings
from django.core.cache import cache

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


PAGES: Final = (
    DemoPage(
        slug="lendcompare",
        partner="LendCompare",
        title="Best personal loans of 2026 | LendCompare",
        headline="The best personal loans for October",
        item_title="LendCompare: best personal loans listing",
        product=Product.PERSONAL_LOAN,
        copy=(
            "Advertiser disclosure: LendCompare receives compensation from ClearPath. ClearPath Personal Loans: "
            "fixed rates from 7.49% to 35.99% APR. The lowest rates go to the most creditworthy applicants. Borrow "
            "$1,000 to $50,000 with terms of 24 to 60 months. Example: a $10,000 loan for 36 months at 12.99% APR "
            "has 36 monthly payments of $336.89. Loans made by ClearPath Financial, NMLS #2099761."
        ),
        edited_copy=(
            "Advertiser disclosure: LendCompare receives compensation from ClearPath. ClearPath Personal Loans: "
            "fixed rates from 5.99% to 35.99% APR. Guaranteed approval in minutes. Borrow $1,000 to $50,000 with "
            "terms of 24 to 60 months. Example: a $10,000 loan for 36 months at 12.99% APR has 36 monthly payments "
            "of $336.89. Loans made by ClearPath Financial, NMLS #2099761."
        ),
        edited_headline="Top personal loans this week",
        edit_summary="The partner lowers the starting APR to 5.99% and adds 'Guaranteed approval in minutes.'",
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
            "Advertisement. CardScout is paid by ClearPath for this listing. The ClearPath Card: 19.99% to 29.99% "
            "variable purchase APR, based on your creditworthiness. $0 annual fee. 3% balance transfer fee. Issued "
            "by Lakeside Bank."
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
        copy=(
            "Sponsored by ClearPath. BudgetBee earns a fee if you apply. Consolidate high-interest debt with a "
            "ClearPath personal loan: fixed rates from 7.49% to 35.99% APR, terms of 24 to 60 months, and no "
            "prepayment penalty. The lowest rates go to the most creditworthy applicants. Loans made by ClearPath "
            "Financial, NMLS #2099761."
        ),
        edited_copy=(
            "Sponsored by ClearPath.\nBudgetBee earns a fee if you apply.\n\nConsolidate high-interest debt with a "
            "ClearPath personal loan: fixed rates from 7.49% to 35.99% APR, terms of 24 to 60 months, and no "
            "prepayment penalty.\nThe lowest rates go to the most creditworthy applicants. Loans made by ClearPath "
            "Financial, NMLS #2099761."
        ),
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


def reset_demo_pages() -> None:
    """Every demo page back to its original (for the admin "Reset demo")."""
    cache.delete_many([_KEY.format(slug=p.slug) for p in PAGES])
