from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from django.db.models import Exists, OuterRef, QuerySet, Subquery

from accounts.models import User
from checks.engine import Span, TermsRefDraft
from checks.models import TermsRef
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import CreditCardTerms, ItemStatus, PersonalLoanTerms, Product, VersionOrigin
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

# Statuses the fan-out acts on: approved items are sent back; items already in needs_rereview get a fresh generated
# version (their content is live on the old numbers too, and without one they could neither be fast-tracked nor
# reaffirmed: E's approval gate refuses copy quoting superseded terms).
AFFECTED_STATUSES: Final = (ItemStatus.APPROVED, ItemStatus.NEEDS_REREVIEW)


@dataclass(frozen=True)
class AffectedApproval:
    """An item whose copy quotes an offer-terms version that is no longer in effect.

    - `approved`: its approved version (the version of its latest approving decision; Foundation: an item quotes v12
      if that version has TermsRefs to v12) quotes superseded terms.
    - `needs_rereview`: its current version quotes superseded terms, and that version is the approved one or a
      generated fast-track version (a later terms change overtook it). A version the marketer or a reviewer wrote
      during the re-review is left to the normal lane.

    `version_*`, `content_text` and `refs` always describe the approved version: fast-track renders from the text
    a human approved, never from an earlier generated version.
    """

    item_id: int
    status: ItemStatus
    version_id: int
    version_n: int
    content_text: str
    refs: tuple[TermsRefDraft, ...]
    quoted_terms_ids: tuple[int, ...]


@dataclass(frozen=True)
class _Candidate:
    item_id: int
    status: ItemStatus
    approved_version_id: int
    checked_version_id: int


def _candidates(items: QuerySet[ReviewItem]) -> list[_Candidate]:
    latest = (
        Decision.objects.filter(item=OuterRef("pk"), outcome__in=APPROVED_OUTCOMES)
        .order_by("-decided_at", "-pk")
        .values("version_id")[:1]
    )
    rows = (
        items.annotate(approved_version_id=Subquery(latest))
        .values_list("pk", "status", "approved_version_id", "current_version_id", "current_version__origin")
        .order_by("pk")
    )
    out = []
    for item_id, status, approved_id, current_id, current_origin in rows:
        if approved_id is None:
            continue
        if status == ItemStatus.APPROVED:
            checked = approved_id
        elif current_id == approved_id or current_origin == VersionOrigin.FAST_TRACK:
            checked = current_id
        else:
            continue
        out.append(_Candidate(item_id, ItemStatus(status), approved_id, checked))
    return out


def affected_approvals(
    *,
    product: Product,
    clock: Clock = SYSTEM_CLOCK,
    item_ids: Iterable[int] | None = None,
    if_published_now: bool = False,
    statuses: Iterable[ItemStatus] = AFFECTED_STATUSES,
) -> tuple[AffectedApproval, ...]:
    """Non-legacy items of `product` (optionally only `item_ids`) whose copy quotes a terms version not in effect
    now (see `AffectedApproval`), ordered by item id. Four queries whatever the item count.

    `if_published_now` (the impact preview): as if a new version took effect now, so every version counts as
    superseded and any quoted terms make the item affected. `statuses` narrows the statuses considered (a subset of
    `AFFECTED_STATUSES`)."""
    wanted_statuses = [s.value for s in statuses if s in AFFECTED_STATUSES]
    items = ReviewItem.objects.filter(status__in=wanted_statuses, is_legacy=False, product=product)
    if item_ids is not None:
        items = items.filter(pk__in=list(item_ids))
    candidates = _candidates(items)
    if not candidates:
        return ()
    now = clock.now()
    wanted = {c.approved_version_id for c in candidates} | {c.checked_version_id for c in candidates}
    refs_by_version: dict[int, list[TermsRef]] = {}
    for ref in (
        TermsRef.objects.filter(version_id__in=wanted)
        .select_related("offer_terms")
        .order_by("span_start", "span_end", "pk")
    ):
        refs_by_version.setdefault(ref.version_id, []).append(ref)  # pyrefly: ignore[missing-attribute]

    def superseded(ref: TermsRef) -> bool:
        return if_published_now or not _in_effect(ref.offer_terms, now)

    stale = [c for c in candidates if any(superseded(r) for r in refs_by_version.get(c.checked_version_id, []))]
    versions = {
        v.pk: v
        for v in Version.objects.filter(pk__in={c.approved_version_id for c in stale}).only("id", "n", "content_text")
    }
    out = []
    for c in stale:
        refs = refs_by_version.get(c.approved_version_id, [])
        version = versions[c.approved_version_id]
        out.append(
            AffectedApproval(
                item_id=c.item_id,
                status=c.status,
                version_id=version.pk,
                version_n=version.n,
                content_text=version.content_text,
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


# --- in-flight items quoting superseded terms (the publish re-check's work list) --------------------------------

# Under review or about to be (walkthrough S20): their copy isn't regenerated (ledger ruling), but the rate-value
# code checks must see the new terms before anyone tries to approve. Approved and needs_rereview items are the
# fan-out's (`AFFECTED_STATUSES`).
IN_FLIGHT_STATUSES: Final = (ItemStatus.SUBMITTED, ItemStatus.IN_REVIEW, ItemStatus.CHANGES_REQUESTED)


def in_flight_quoting_superseded(
    *, product: Product, clock: Clock = SYSTEM_CLOCK, item_ids: Iterable[int] | None = None
) -> tuple[int, ...]:
    """Ids of non-legacy in-flight items of `product` (optionally only `item_ids`) whose current version quotes a
    terms version not in effect now, ordered by id. One query."""
    stale_refs = TermsRef.objects.filter(version_id=OuterRef("current_version_id")).exclude(
        offer_terms__effective_range__contains=clock.now()
    )
    items = ReviewItem.objects.filter(
        status__in=[s.value for s in IN_FLIGHT_STATUSES], is_legacy=False, product=product
    ).filter(Exists(stale_refs))
    if item_ids is not None:
        items = items.filter(pk__in=list(item_ids))
    return tuple(items.order_by("pk").values_list("pk", flat=True))
