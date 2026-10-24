"""Fixtures for the review workflow: current offer terms and items driven through the real services."""

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange

from accounts.models import User
from core.clock import FixedClock
from core.domain import Channel, CheckStatus, CreditCardTerms, Market, PersonalLoanTerms, Product
from reviews.models import ReviewItem
from reviews.services import SubmitItemInput, SubmitItemResult, submit_item
from terms.models import OfferTerms

PL_VALUES = PersonalLoanTerms(
    apr_min=Decimal("7.49"),
    apr_max=Decimal("35.99"),
    amount_min=Decimal(1000),
    amount_max=Decimal(50000),
    term_months=(24, 36, 48, 60),
    origination_fee_min_pct=Decimal(0),
    origination_fee_max_pct=Decimal(8),
)
CC_VALUES = CreditCardTerms(
    purchase_apr_min=Decimal("19.99"),
    purchase_apr_max=Decimal("29.99"),
    balance_transfer_fee_pct=Decimal(3),
    annual_fee=Decimal(0),
    issuing_bank="Lakeside Bank",
)

# Clean enough for the code rules: no trigger terms, so a submission raises no blocking code findings.
CLEAN_COPY = "Personal loans from ClearPath. Apply online in minutes."
# A personal-loan claim with a rate range: yields TermsRefs to the current PL terms.
RATE_COPY = "Personal loans with rates from 7.49% APR to 35.99% APR. Apply online in minutes."

type Submit = Callable[..., SubmitItemResult]


@pytest.fixture
def pl_terms(lead: User, clock: FixedClock) -> OfferTerms:
    """PL v1, in effect from 30 days before the test clock, open-ended."""
    return OfferTerms.objects.create(
        product=Product.PERSONAL_LOAN,
        version=1,
        effective_range=DateTimeTZRange(clock.now() - timedelta(days=30), None, "[)"),
        values=PL_VALUES.model_dump(mode="json"),
        created_by=lead,
        created_at=clock.now() - timedelta(days=30),
    )


def dismiss_all(item_id: int, actor: User, clock: FixedClock, reason: str = "Checked: fine") -> None:
    """Dismiss every open finding on the item's current version, through the triage service."""
    from checks.models import Finding
    from checks.services import dismiss_finding

    item = ReviewItem.objects.get(pk=item_id)
    for finding_id in Finding.objects.filter(version_id=item.current_version_id, state="open").values_list(  # pyrefly: ignore[missing-attribute]
        "pk", flat=True
    ):
        dismiss_finding(actor=actor, finding_id=finding_id, reason=reason, clock=clock)


def ai_done(item_id: int, status: CheckStatus = CheckStatus.SUCCEEDED) -> None:
    """Stand-in for workstream D's handler finishing the AI check."""
    ReviewItem.objects.filter(pk=item_id).update(llm_check_status=status)


def approve(item_id: int, reviewer: User, clock: FixedClock) -> int:
    """Triage everything, finish the AI check, and approve the current version through the services."""
    from core.domain import DecisionOutcome
    from reviews.decisions import DecisionInput, record_decision

    dismiss_all(item_id, reviewer, clock)
    ai_done(item_id)
    item = ReviewItem.objects.select_related("current_version").get(pk=item_id)
    n = item.current_version.n if item.current_version else 0
    data = DecisionInput(outcome=DecisionOutcome.APPROVED, version_n=n, reason="Meets policy")
    return record_decision(actor=reviewer, item_id=item_id, data=data, clock=clock).decision_id


@pytest.fixture
def approved(submit: "Submit", reviewer: User, clock: FixedClock) -> ReviewItem:
    """An approved landing page (12-month expiry), assigned to `reviewer`, no placements yet."""
    item_id = submit().item_id
    approve(item_id, reviewer, clock)
    return ReviewItem.objects.get(pk=item_id)


@pytest.fixture
def submit(marketer: User, clock: FixedClock) -> Submit:
    """Submit through the real service; keyword overrides go to SubmitItemInput."""

    def run(*, actor: User | None = None, **overrides: object) -> SubmitItemResult:
        fields: dict[str, object] = {
            "title": "Spring PL email",
            "product": Product.PERSONAL_LOAN,
            "channel": Channel.LANDING_PAGE,
            "markets": (Market.NATIONAL,),
            "content_text": CLEAN_COPY,
            "planned_first_run": date(2026, 11, 1),
        }
        fields.update(overrides)
        return submit_item(
            actor=actor or marketer,
            data=SubmitItemInput(**fields),  # pyrefly: ignore[bad-argument-type]
            clock=clock,
        )

    return run
