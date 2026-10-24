from django.http import HttpRequest
from ninja import Router, Status

from core.domain import Product
from core.errors import NotImplementedYet
from core.schemas import ERRORS, STUB_ERRORS
from terms import selectors
from terms.schemas import ImpactPreviewIn, ImpactPreviewOut, OfferTermsOut, OfferTermsPublishIn

router = Router(tags=["terms"])


@router.get("/terms", response={200: list[OfferTermsOut], **ERRORS}, operation_id="listOfferTerms")
def list_terms(request: HttpRequest, product: Product | None = None) -> list[selectors.OfferTermsRow]:
    """Every version, newest first per product."""
    return list(selectors.list_offer_terms(product=product))


@router.get("/terms/current", response={200: list[OfferTermsOut], **ERRORS}, operation_id="getCurrentOfferTerms")
def current_terms(request: HttpRequest) -> list[selectors.OfferTermsRow]:
    return list(selectors.current_offer_terms())


@router.get("/terms/{int:terms_id}", response={200: OfferTermsOut, **ERRORS}, operation_id="getOfferTerms")
def get_terms(request: HttpRequest, terms_id: int) -> selectors.OfferTermsRow:
    return selectors.get_offer_terms(terms_id=terms_id)


@router.post(
    "/terms/impact-preview", response={200: ImpactPreviewOut, **STUB_ERRORS}, operation_id="previewTermsImpact"
)
def impact_preview(request: HttpRequest, body: ImpactPreviewIn) -> ImpactPreviewOut:
    """Which approved items and partners a new version would affect, before saving. [workstream F]"""
    raise NotImplementedYet("terms impact preview")


@router.post("/terms", response={201: OfferTermsOut, **STUB_ERRORS}, operation_id="publishOfferTerms")
def publish_terms(request: HttpRequest, body: OfferTermsPublishIn) -> Status[OfferTermsOut]:
    """Save a new version: generates fast-track versions and moves affected items to needs_rereview or expired.
    Overlapping ranges fail with 409 terms_range_overlap. Leads only. [workstream F]"""
    raise NotImplementedYet("publishing offer terms")
