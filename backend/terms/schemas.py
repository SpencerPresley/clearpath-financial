from datetime import datetime

from ninja import Schema
from pydantic import Field

from core.domain import ItemStatus, OfferTermsValues, Product, TermsField
from reviews.schemas import ItemRowOut, PartyRefOut


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
    note: str = Field(default="", max_length=2000)


class ImpactPreviewIn(Schema):
    product: Product
    values: OfferTermsValues


class AffectedItemOut(Schema):
    item: ItemRowOut
    is_live: bool
    quoted_fields: list[TermsField]
    will_become: ItemStatus = Field(description="needs_rereview if live, expired if not (ruling 2).")


class AffectedPartnerOut(Schema):
    partner: PartyRefOut
    item_count: int


class ImpactPreviewOut(Schema):
    """'14 approved items quote v12; 9 will need re-review' before the lead confirms."""

    current_terms_id: int | None
    approved_items_quoting: int
    will_need_rereview: int
    will_expire: int
    changed_fields: list[TermsField]
    items: list[AffectedItemOut]
    partners: list[AffectedPartnerOut]
