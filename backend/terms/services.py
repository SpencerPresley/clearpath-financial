"""Publishing offer terms (spec §4.3 "Offer terms"; product-spec Automation "New OfferTerms version").

`publish_terms` is the only writer of OfferTerms. It closes the version in effect and inserts the next one at the
same instant, so the EXCLUDE constraint's "exactly one version in effect" holds, and records TERMS_PUBLISHED. The
re-review fan-out runs from that event (`terms.handlers`), one item per transaction.
"""

from dataclasses import dataclass
from typing import Final

from django.db import IntegrityError, connection, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Max

from accounts.models import User
from audit.payloads import TermsPublishedPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.db import constraint_name
from core.domain import CreditCardTerms, EntityType, EventType, PersonalLoanTerms, Product, Role
from core.errors import Conflict, InvalidInput, TermsRangeOverlap
from core.permissions import require_role
from terms.models import OfferTerms
from terms.selectors import affected_approvals

# pg_advisory_xact_lock(classid, objid): "CPTR" as a big-endian int, then the product's position in Product.
# Serializes publishes per product so two leads can't both close the same open range.
TERMS_LOCK_CLASS: Final = 0x4350_5452


@dataclass(frozen=True)
class PublishTermsInput:
    product: Product
    values: PersonalLoanTerms | CreditCardTerms
    based_on_terms_id: int | None  # the version the lead's form showed; None for a product's first terms
    note: str = ""


def _lock(product: Product) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [TERMS_LOCK_CLASS, list(Product).index(product)])


def publish_terms(*, actor: User, data: PublishTermsInput, clock: Clock = SYSTEM_CLOCK) -> int:
    """A new version of `data.product`'s terms, in effect from now; the previous version's range closes at the
    same instant. Leads only. Returns the new OfferTerms id.

    Refused: values for another product; values identical to the version in effect (publishing them would send
    every quoting item to re-review for nothing); and a stale `based_on_terms_id` (409 conflict: another lead
    published since this lead's form and impact preview loaded, and saving would silently revert their change).
    The event lists the items quoting the now-superseded
    version; the fan-out handler recomputes that list when it runs, so the payload is the audit record, not the
    work queue.
    """
    require_role(actor, Role.LEAD)
    if data.values.product != data.product:
        raise InvalidInput.for_field("values", f"These values are for {data.values.product}, not {data.product}.")
    with transaction.atomic():
        _lock(data.product)  # serializes publishers; no row lock, which would stall ref inserts (FK key-share)
        now = clock.now()  # after the lock: a publisher that waited must not close a range before it opened
        previous = OfferTerms.objects.filter(product=data.product, effective_range__upper_inf=True).first()
        if (previous.pk if previous is not None else None) != data.based_on_terms_id:
            current = f"v{previous.version}" if previous is not None else "no version"
            raise Conflict(
                f"The offer terms changed since you opened this ({current} is in effect now). Review the impact again.",
                details={"current_terms_id": previous.pk if previous is not None else None},
            )
        if previous is not None and previous.typed_values == data.values:
            raise InvalidInput.for_field("values", f"Nothing changed: these are v{previous.version}'s values.")
        if previous is not None:
            lower = previous.effective_range.lower  # pyrefly: ignore[missing-attribute]
            if lower >= now:
                raise TermsRangeOverlap(
                    f"v{previous.version} takes effect at {lower.isoformat()}; publish after that.",
                    details={"offer_terms_id": previous.pk},
                )
            OfferTerms.objects.filter(pk=previous.pk).update(effective_range=DateTimeTZRange(lower, now, "[)"))
        version = (OfferTerms.objects.filter(product=data.product).aggregate(n=Max("version"))["n"] or 0) + 1
        try:
            with transaction.atomic():
                terms = OfferTerms.objects.create(
                    product=data.product,
                    version=version,
                    effective_range=DateTimeTZRange(now, None, "[)"),
                    values=data.values.model_dump(mode="json"),
                    note=data.note,
                    created_by=actor,
                    created_at=now,
                )
        except IntegrityError as exc:
            if constraint_name(exc) == "terms_no_overlap":
                raise TermsRangeOverlap("Another version is already in effect from then.") from exc
            raise
        affected = affected_approvals(product=data.product, clock=clock)
        record_event(
            type=EventType.TERMS_PUBLISHED,
            entity=EntityType.OFFER_TERMS,
            entity_id=terms.pk,
            payload=TermsPublishedPayload(
                offer_terms_id=terms.pk,
                product=data.product,
                version=version,
                previous_offer_terms_id=previous.pk if previous is not None else None,
                affected_item_ids=tuple(a.item_id for a in affected),
            ),
            actor=actor,
            at=now,
        )
    return terms.pk
