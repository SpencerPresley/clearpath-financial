from datetime import datetime

from ninja import Schema
from pydantic import Field

from core.domain import ItemStatus, OfferTermsValues, Product, TermsField
from reviews.schemas import ItemRowOut, PartyRefOut
from terms.impact import FastTrackLane


class OfferTermsOut(Schema):
    id: int
    product: Product
    version: int
    effective_from: datetime
    effective_to: datetime | None = Field(description="Null for the version in effect now.")
    values: OfferTermsValues
    note: str
    created_by_id: int
    created_by_name: str
    created_at: datetime
    is_current: bool


class OfferTermsPublishIn(Schema):
    """A new version of a product's terms. It takes effect now and closes the current version's range at the same
    instant. Values identical to the version in effect are refused (422 on `values`)."""

    product: Product
    values: OfferTermsValues
    based_on_terms_id: int | None = Field(
        description="The version in effect when the lead opened the form (null for a product's first terms). If "
        "another version was published since, the save is refused with 409 conflict: re-run the preview."
    )
    note: str = Field(default="", max_length=2000)


class ImpactPreviewIn(Schema):
    product: Product
    values: OfferTermsValues


class AffectedItemOut(Schema):
    item: ItemRowOut
    is_live: bool
    quoted_fields: list[TermsField]
    will_become: ItemStatus = Field(
        description="needs_rereview if live, expired if not (ruling 2); items already in needs_rereview stay there."
    )
    lane: FastTrackLane = Field(
        description="fast_track: a version with the new numbers is generated for one-click approval. normal: the "
        "quoted numbers no longer fit the copy, so it's re-reviewed in full."
    )
    numbers_change: bool = Field(
        description="False when none of the numbers this item quotes change (the generated version has no diff)."
    )


class AffectedPartnerOut(Schema):
    partner: PartyRefOut
    item_count: int


class ImpactPreviewOut(Schema):
    """'14 approved items quote v12; 9 will need re-review, 5 will expire.' before the lead confirms."""

    current_terms_id: int | None
    current_version: int | None = Field(description="The version in effect now; null for a product's first terms.")
    next_version: int
    approved_items_quoting: int
    will_need_rereview: int = Field(description="Approved and live: back to the reviewer in the fast-track lane.")
    will_expire: int = Field(description="Approved, not live: expired; the next round starts from the new numbers.")
    already_in_rereview: int = Field(description="Already in needs_rereview; they get a generated version too.")
    normal_lane: int = Field(description="Affected items that can't be fast-tracked (lane normal).")
    changed_fields: list[TermsField]
    summary: str = Field(examples=["14 approved items quote v12; 9 will need re-review, 5 will expire."])
    items: list[AffectedItemOut]
    partners: list[AffectedPartnerOut]


class FastTrackIn(Schema):
    version_n: int = Field(description="The generated version the reviewer looked at; stale if a newer one exists.")
    reason: str = Field(min_length=1, max_length=2000)


class SeenVersionIn(Schema):
    item_id: int
    version_n: int


class BulkFastTrackIn(Schema):
    item_ids: list[int] = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)
    seen_versions: list[SeenVersionIn] = Field(
        default_factory=list,
        max_length=500,
        description=(
            "The generated version each item showed when the lead chose it. Send it: an item listed here is "
            "approved only at that version (else skipped as stale_version); an item without an entry is approved "
            "at whatever version is current, which a later terms change may have replaced unseen."
        ),
    )
