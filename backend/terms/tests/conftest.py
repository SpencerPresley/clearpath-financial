"""Fixtures for offer-terms tests: E's review-workflow fixtures (current PL terms, submit, approve), plus helpers
to publish a new version and put an item live."""

from decimal import Decimal

from accounts.models import User
from core.clock import FixedClock
from core.domain import PersonalLoanTerms
from reviews.models import ReviewItem
from reviews.placements import PlacementInput, record_placement
from reviews.tests.conftest import PL_VALUES, approve, approved, pl_terms, submit
from terms.services import PublishTermsInput, publish_terms

__all__ = ["PL_VALUES", "approve", "approved", "pl_terms", "submit"]

# The worked example (decisions.md "Rates are stored once"): at the 7.49% floor the payment is $311; when the floor
# moves to 12.99%, fast-track rewrites both numbers and the payment becomes $337. The qualifier sentence keeps
# pricing.creditworthiness_qualifier quiet, so v+1 raises nothing new and one click approves it.
WORKED_EXAMPLE = (
    "Personal loans from ClearPath. Representative example: a $10,000 loan over 36 months at 7.49% APR has "
    "36 monthly payments of $311. Rates from 7.49% APR to 35.99% APR. Your rate depends on your "
    "creditworthiness; the lowest rates are for the most qualified applicants."
)
# Same claims without the qualifier: the warning quotes "from 7.49%", a span fast-track rewrites, so the dismissal
# made on v1 doesn't carry and v+1 comes back with an open finding (the normal lane).
UNQUALIFIED = (
    "Representative example: a $10,000 loan over 36 months at 7.49% APR has 36 monthly payments of $311. "
    "Rates from 7.49% APR to 35.99% APR."
)
NEW_FLOOR = PL_VALUES.model_copy(update={"apr_min": Decimal("12.99")})


def publish(lead: User, clock: FixedClock, values: PersonalLoanTerms = NEW_FLOOR) -> int:
    return publish_terms(actor=lead, data=PublishTermsInput(product=values.product, values=values), clock=clock)


def go_live(item: ReviewItem, marketer: User, clock: FixedClock) -> None:
    record_placement(
        actor=marketer,
        item_id=item.pk,
        data=PlacementInput(location="LoanFinder", first_run=clock.today()),
        clock=clock,
    )
