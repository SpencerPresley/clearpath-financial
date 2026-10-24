"""The impact preview a lead sees before publishing new offer terms (spec §4.3; product-spec Screens "Offer terms":
"14 approved items quote v12; 9 will need re-review"). Read-only: it dry-runs the fan-out's render against the
proposed values and writes nothing."""

from dataclasses import dataclass
from enum import StrEnum

from accounts.models import User
from checks.engine import StaleTermsRef, render_fast_track
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import CreditCardTerms, ItemStatus, PersonalLoanTerms, Product, Role, TermsField
from core.errors import InvalidInput
from core.permissions import require_role
from reviews.models import Placement, ReviewItem
from reviews.selectors import ItemRow, PartyRef, item_row, live_placements_q, row_queryset
from terms.selectors import AffectedApproval, affected_approvals, terms_in_effect


class FastTrackLane(StrEnum):
    FAST_TRACK = "fast_track"  # a version with the new numbers will be generated for one-click approval
    NORMAL = "normal"  # the quoted numbers no longer fit the copy; a reviewer re-reviews it in full


@dataclass(frozen=True)
class AffectedItem:
    item: ItemRow
    is_live: bool
    quoted_fields: tuple[TermsField, ...]
    will_become: ItemStatus
    lane: FastTrackLane
    numbers_change: bool


@dataclass(frozen=True)
class AffectedPartner:
    partner: PartyRef
    item_count: int


@dataclass(frozen=True)
class ImpactPreview:
    current_terms_id: int | None
    current_version: int | None
    next_version: int
    approved_items_quoting: int
    will_need_rereview: int
    will_expire: int
    already_in_rereview: int
    normal_lane: int
    changed_fields: tuple[TermsField, ...]
    summary: str
    items: tuple[AffectedItem, ...]
    partners: tuple[AffectedPartner, ...]


def _changed_fields(
    old: PersonalLoanTerms | CreditCardTerms | None, new: PersonalLoanTerms | CreditCardTerms
) -> tuple[TermsField, ...]:
    if old is None:
        return ()
    fields = {f.value for f in TermsField}
    return tuple(
        TermsField(name)
        for name in type(new).model_fields
        if name in fields and getattr(old, name) != getattr(new, name)
    )


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _summary(*, version: int | None, quoting: int, rereview: int, expire: int, already: int) -> str:
    """'14 approved items quote v12; 9 will need re-review, 5 will expire.'"""
    label = f"v{version}" if version is not None else "the current terms"
    if quoting == 0:
        head = f"No approved items quote {label}."
    else:
        verb = "quotes" if quoting == 1 else "quote"
        outcomes = [f"{rereview} will need re-review"] if rereview else []
        outcomes += [f"{expire} will expire"] if expire else []
        head = f"{_plural(quoting, 'approved item', 'approved items')} {verb} {label}; {', '.join(outcomes)}."
    if already:
        head += f" {_plural(already, 'item', 'items')} already in re-review will get the new numbers."
    return head


def _lane(approval: AffectedApproval, values: PersonalLoanTerms | CreditCardTerms) -> tuple[FastTrackLane, bool]:
    try:
        text = render_fast_track(approval.content_text, approval.refs, values)
    except StaleTermsRef:  # decide here: the preview reports the normal lane, as the fan-out will take it
        return FastTrackLane.NORMAL, True
    return FastTrackLane.FAST_TRACK, text != approval.content_text


def impact_preview(
    *, viewer: User, product: Product, values: PersonalLoanTerms | CreditCardTerms, clock: Clock = SYSTEM_CLOCK
) -> ImpactPreview:
    """What publishing `values` for `product` now would do. Leads only. A fixed number of queries.

    Unchanged values preview nothing (publishing them is refused)."""
    require_role(viewer, Role.LEAD)
    if values.product != product:
        raise InvalidInput.for_field("values", f"These values are for {values.product}, not {product}.")
    current = terms_in_effect(product=product, clock=clock)
    old_values = current.typed_values if current is not None else None
    changed = _changed_fields(old_values, values)
    unchanged = old_values == values
    approvals = () if unchanged else affected_approvals(product=product, clock=clock, if_published_now=True)
    ids = [a.item_id for a in approvals]
    rows = {i.pk: item_row(i, now=clock.now()) for i in row_queryset(ReviewItem.objects.filter(pk__in=ids))}
    live = set(
        Placement.objects.filter(live_placements_q(clock.today()), item_id__in=ids).values_list("item_id", flat=True)
    )
    items: list[AffectedItem] = []
    for approval in approvals:
        lane, numbers_change = _lane(approval, values)
        is_live = approval.item_id in live
        if approval.status is ItemStatus.NEEDS_REREVIEW:
            will_become = ItemStatus.NEEDS_REREVIEW
        else:
            will_become = ItemStatus.NEEDS_REREVIEW if is_live else ItemStatus.EXPIRED
        items.append(
            AffectedItem(
                item=rows[approval.item_id],
                is_live=is_live,
                quoted_fields=tuple(dict.fromkeys(TermsField(r.field) for r in approval.refs)),
                will_become=will_become,
                lane=lane,
                numbers_change=numbers_change,
            )
        )
    approved = [i for i in items if i.item.status is ItemStatus.APPROVED]
    rereview = sum(1 for i in approved if i.will_become is ItemStatus.NEEDS_REREVIEW)
    expire = len(approved) - rereview
    already = len(items) - len(approved)
    partners: dict[int, tuple[PartyRef, int]] = {}
    for i in items:
        if i.item.partner is not None:
            ref, n = partners.get(i.item.partner.id, (i.item.partner, 0))
            partners[ref.id] = (ref, n + 1)
    current_version = current.version if current is not None else None
    summary = (
        f"These are v{current_version}'s values; nothing would change."
        if unchanged
        else _summary(version=current_version, quoting=len(approved), rereview=rereview, expire=expire, already=already)
    )
    return ImpactPreview(
        current_terms_id=current.pk if current is not None else None,
        current_version=current_version,
        next_version=(current_version or 0) + 1,
        approved_items_quoting=len(approved),
        will_need_rereview=rereview,
        will_expire=expire,
        already_in_rereview=already,
        normal_lane=sum(1 for i in items if i.lane is FastTrackLane.NORMAL),
        changed_fields=changed,
        summary=summary,
        items=tuple(items),
        partners=tuple(
            AffectedPartner(partner=ref, item_count=n)
            for ref, n in sorted(partners.values(), key=lambda p: (-p[1], p[0].name))
        ),
    )
