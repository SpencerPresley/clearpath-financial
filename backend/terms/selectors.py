from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from django.db.models import OuterRef, QuerySet, Subquery

from accounts.models import User
from checks.engine import Span, TermsRefDraft
from checks.models import TermsRef
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import CreditCardTerms, ItemStatus, PersonalLoanTerms, Product
from core.errors import NotFound
from reviews.models import APPROVED_OUTCOMES, Decision, ReviewItem, Version
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


def terms_in_effect(*, product: Product, clock: Clock = SYSTEM_CLOCK) -> OfferTerms | None:
    return OfferTerms.objects.filter(product=product, effective_range__contains=clock.now()).first()


# --- approvals quoting superseded terms (the fan-out's and the impact preview's work list) ----------------------


@dataclass(frozen=True)
class AffectedApproval:
    """An approved item whose approved version quotes an offer-terms version that is no longer in effect.

    "Approved version" is the version of the item's latest approving decision (Foundation: an item quotes v12 if
    that version has TermsRefs to v12), not its current version. `refs` are all of that version's TermsRefs, in
    the shape `render_fast_track` takes.
    """

    item_id: int
    version_id: int
    version_n: int
    content_text: str
    refs: tuple[TermsRefDraft, ...]
    quoted_terms_ids: tuple[int, ...]


def _approved_version_ids(items: QuerySet[ReviewItem]) -> dict[int, int]:
    latest = (
        Decision.objects.filter(item=OuterRef("pk"), outcome__in=APPROVED_OUTCOMES)
        .order_by("-decided_at", "-pk")
        .values("version_id")[:1]
    )
    rows = items.annotate(approved_version_id=Subquery(latest)).values_list("pk", "approved_version_id")
    return {item_id: version_id for item_id, version_id in rows if version_id is not None}


def affected_approvals(
    *, product: Product, clock: Clock = SYSTEM_CLOCK, item_ids: Iterable[int] | None = None
) -> tuple[AffectedApproval, ...]:
    """Approved, non-legacy items of `product` (optionally only `item_ids`) whose approved version has TermsRefs to
    a version not in effect now, ordered by item id. A fixed number of queries whatever the item count."""
    items = ReviewItem.objects.filter(status=ItemStatus.APPROVED.value, is_legacy=False, product=product)
    if item_ids is not None:
        items = items.filter(pk__in=list(item_ids))
    approved = _approved_version_ids(items)
    if not approved:
        return ()
    now = clock.now()
    refs_by_version: dict[int, list[TermsRef]] = {}
    for ref in (
        TermsRef.objects.filter(version_id__in=approved.values())
        .select_related("offer_terms")
        .order_by("span_start", "span_end", "pk")
    ):
        refs_by_version.setdefault(ref.version_id, []).append(ref)  # pyrefly: ignore[missing-attribute]
    stale_versions = {
        version_id
        for version_id, refs in refs_by_version.items()
        if any(not _in_effect(ref.offer_terms, now) for ref in refs)
    }
    versions = {
        v.pk: v for v in Version.objects.filter(pk__in=stale_versions).only("id", "n", "content_text", "item_id")
    }
    out = []
    for item_id, version_id in sorted(approved.items()):
        if version_id not in stale_versions:
            continue
        refs = refs_by_version[version_id]
        out.append(
            AffectedApproval(
                item_id=item_id,
                version_id=version_id,
                version_n=versions[version_id].n,
                content_text=versions[version_id].content_text,
                refs=tuple(
                    TermsRefDraft(field=r.field, span=Span(r.span_start, r.span_end), quoted_value=r.quoted_value)
                    for r in refs
                ),
                quoted_terms_ids=tuple(sorted({r.offer_terms.pk for r in refs})),
            )
        )
    return tuple(out)


def _in_effect(terms: OfferTerms, at: datetime) -> bool:
    rng = terms.effective_range
    lower, upper = rng.lower, rng.upper  # pyrefly: ignore[missing-attribute]
    return lower <= at and (upper is None or at < upper)
