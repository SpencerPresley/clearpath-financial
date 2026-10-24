from dataclasses import dataclass
from datetime import datetime

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import CreditCardTerms, PersonalLoanTerms, Product
from core.errors import NotFound
from terms.models import OfferTerms


@dataclass(frozen=True)
class OfferTermsRow:
    id: int
    product: Product
    version: int
    effective_from: datetime
    effective_to: datetime | None  # None: open-ended (the current version)
    values: PersonalLoanTerms | CreditCardTerms
    note: str
    created_by_id: int
    created_by_name: str
    created_at: datetime
    is_current: bool


def _row(terms: OfferTerms, now: datetime) -> OfferTermsRow:
    created_by: User = terms.created_by
    rng = terms.effective_range
    lower, upper = rng.lower, rng.upper  # pyrefly: ignore[missing-attribute]
    return OfferTermsRow(
        id=terms.pk,
        product=Product(terms.product),
        version=terms.version,
        effective_from=lower,
        effective_to=upper,
        values=terms.typed_values,
        note=terms.note,
        created_by_id=created_by.pk,
        created_by_name=created_by.display_name or created_by.email,
        created_at=terms.created_at,
        is_current=lower <= now and (upper is None or now < upper),
    )


def list_offer_terms(*, product: Product | None = None, clock: Clock = SYSTEM_CLOCK) -> tuple[OfferTermsRow, ...]:
    qs = OfferTerms.objects.select_related("created_by").order_by("product", "-version")
    if product is not None:
        qs = qs.filter(product=product)
    now = clock.now()
    return tuple(_row(t, now) for t in qs)


def current_offer_terms(*, clock: Clock = SYSTEM_CLOCK) -> tuple[OfferTermsRow, ...]:
    """The version in effect now, per product that has rate terms."""
    now = clock.now()
    qs = OfferTerms.objects.filter(effective_range__contains=now).select_related("created_by").order_by("product")
    return tuple(_row(t, now) for t in qs)


def get_offer_terms(*, terms_id: int, clock: Clock = SYSTEM_CLOCK) -> OfferTermsRow:
    terms = OfferTerms.objects.select_related("created_by").filter(pk=terms_id).first()
    if terms is None:
        raise NotFound.entity("offer terms", terms_id)
    return _row(terms, clock.now())
