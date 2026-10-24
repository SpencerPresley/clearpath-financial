from django.http import HttpRequest
from ninja import File, Form, Router, Status, UploadedFile

from accounts.api import current_user
from core.domain import AttachmentKind, PartnerStatus
from core.schemas import ERRORS
from partners import selectors, services
from partners.schemas import PartnerDetailOut, PartnerIn, PartnerRowOut, PartnerUpdateIn
from reviews import records
from reviews import services as review_services
from reviews.schemas import AttachmentOut

router = Router(tags=["partners"])


@router.get("/partners", response={200: list[PartnerRowOut], **ERRORS}, operation_id="listPartners")
def list_partners(
    request: HttpRequest, status: PartnerStatus | None = None, q: str | None = None
) -> list[selectors.PartnerRow]:
    return list(selectors.list_partners(status=status, q=q))


@router.post("/partners", response={201: PartnerDetailOut, **ERRORS}, operation_id="createPartner")
def create_partner(request: HttpRequest, body: PartnerIn) -> Status[selectors.PartnerDetail]:
    partner_id = services.create_partner(
        actor=current_user(request),
        data=services.NewPartner(
            name=body.name,
            type=body.type,
            website=body.website,
            contact_email=body.contact_email,
            agreement_signed_on=body.agreement_signed_on,
            notes=body.notes,
        ),
    )
    return Status(201, selectors.get_partner_detail(partner_id=partner_id))


@router.get("/partners/{int:partner_id}", response={200: PartnerDetailOut, **ERRORS}, operation_id="getPartner")
def get_partner(request: HttpRequest, partner_id: int) -> selectors.PartnerDetail:
    """Agreement and evidence, counts, and repeat issues. Items: `GET /items?partner_id=`."""
    return selectors.get_partner_detail(partner_id=partner_id)


@router.patch("/partners/{int:partner_id}", response={200: PartnerDetailOut, **ERRORS}, operation_id="updatePartner")
def update_partner(request: HttpRequest, partner_id: int, body: PartnerUpdateIn) -> selectors.PartnerDetail:
    services.update_partner(
        actor=current_user(request),
        partner_id=partner_id,
        changes=services.PartnerChanges(**body.model_dump(exclude_unset=True)),
    )
    return selectors.get_partner_detail(partner_id=partner_id)


@router.get(
    "/partners/{int:partner_id}/attachments",
    response={200: list[AttachmentOut], **ERRORS},
    operation_id="listPartnerAttachments",
)
def list_attachments(request: HttpRequest, partner_id: int) -> list[records.AttachmentRow]:
    selectors.get_partner_detail(partner_id=partner_id)  # 404 for an unknown partner
    return list(records.list_partner_attachments(partner_id=partner_id))


@router.post(
    "/partners/{int:partner_id}/attachments",
    response={201: AttachmentOut, **ERRORS},
    operation_id="uploadPartnerAttachment",
)
def upload_attachment(
    request: HttpRequest, partner_id: int, kind: Form[AttachmentKind], file: File[UploadedFile]
) -> Status[records.AttachmentRow]:
    """Agreements and partner evidence. Leads only."""
    ref = review_services.add_attachment(
        actor=current_user(request),
        owner=review_services.AttachmentOwner(kind="partner", id=partner_id),
        kind=kind,
        file=file,
    )
    return Status(201, next(a for a in records.list_partner_attachments(partner_id=partner_id) if a.id == ref.id))
