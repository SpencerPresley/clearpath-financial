from django.http import HttpRequest
from ninja import Router, Status

from accounts.api import current_user
from core.domain import Product
from core.schemas import ERRORS
from reviews import assignment, records
from reviews.schemas import BulkResultOut, DecisionOut
from terms import fast_track, impact, selectors, services
from terms.schemas import (
    BulkFastTrackIn,
    FastTrackIn,
    ImpactPreviewIn,
    ImpactPreviewOut,
    OfferTermsOut,
    OfferTermsPublishIn,
)

router = Router(tags=["terms"])
# Fast-track approval is a decision; it lives here with the fan-out that creates the versions it approves.
fast_track_router = Router(tags=["decisions"])


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


@router.post("/terms/impact-preview", response={200: ImpactPreviewOut, **ERRORS}, operation_id="previewTermsImpact")
def impact_preview(request: HttpRequest, body: ImpactPreviewIn) -> impact.ImpactPreview:
    """Which items and partners publishing `values` now would affect, before saving. Read-only; leads only."""
    return impact.impact_preview(viewer=current_user(request), product=body.product, values=body.values)


@router.post("/terms", response={201: OfferTermsOut, **ERRORS}, operation_id="publishOfferTerms")
def publish_terms(request: HttpRequest, body: OfferTermsPublishIn) -> Status[selectors.OfferTermsRow]:
    """Save a new version, in effect now. Leads only. Every approved item quoting the previous version then gets a
    generated fast-track version (in the background, seconds): live items go to needs_rereview(terms_changed),
    the rest to expired(terms_changed). Unchanged values are 422 on `values`; a stale `based_on_terms_id` (another
    version was published since the form loaded) is 409 conflict."""
    terms_id = services.publish_terms(
        actor=current_user(request),
        data=services.PublishTermsInput(
            product=body.product, values=body.values, based_on_terms_id=body.based_on_terms_id, note=body.note
        ),
    )
    return Status(201, selectors.get_offer_terms(terms_id=terms_id))


# --- fast-track approval ---------------------------------------------------------------------------------------


@fast_track_router.post(
    "/items/{int:item_id}/fast-track-approve", response={201: DecisionOut, **ERRORS}, operation_id="fastTrackApprove"
)
def fast_track_approve(request: HttpRequest, item_id: int, body: FastTrackIn) -> Status[records.DecisionRow]:
    """One-click approval of a needs_rereview item's generated terms-change version (`version_n`, the version the
    reviewer saw; else 409 stale_version). The item's assignee or a lead. The usual gates apply: 409
    open_findings_block_decision, accepted_findings_block_approval, stale_offer_terms; 409 conflict if the current
    version isn't a generated one; 409 invalid_transition unless the item is in needs_rereview."""
    result = fast_track.fast_track_approve(
        actor=current_user(request), item_id=item_id, version_n=body.version_n, reason=body.reason
    )
    return Status(201, records.get_decision(decision_id=result.decision_id))


@fast_track_router.post(
    "/items/bulk/fast-track-approve", response={200: BulkResultOut, **ERRORS}, operation_id="bulkFastTrackApprove"
)
def bulk_fast_track(request: HttpRequest, body: BulkFastTrackIn) -> assignment.BulkResult:
    """Reviewers and leads. Approve each item's current generated version, one item at a time, with the single
    fast-track's checks (a reviewer only their own items). Anything that can't be fast-tracked (open findings, not
    in needs_rereview, a newer version, someone else's item) is listed in `skipped` with its error code and stays in
    the normal lane (ruling 4)."""
    return fast_track.bulk_fast_track_approve(
        actor=current_user(request),
        item_ids=body.item_ids,
        reason=body.reason,
        seen_versions={v.item_id: v.version_n for v in body.seen_versions},
    )
