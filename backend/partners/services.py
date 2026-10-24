"""Partner records. Leads manage partners (product-spec "Roles")."""

from dataclasses import dataclass
from datetime import date

from django.db import transaction

from accounts.models import User
from audit.payloads import FieldChange, PartnerCreatedPayload, PartnerUpdatedPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EntityType, EventType, PartnerStatus, PartnerType, Role
from core.errors import InvalidInput, NotFound
from core.permissions import require_role
from partners.models import Partner


@dataclass(frozen=True)
class NewPartner:
    name: str
    type: PartnerType
    website: str = ""
    contact_email: str = ""
    agreement_signed_on: date | None = None
    notes: str = ""


@dataclass(frozen=True)
class PartnerChanges:
    """None means "leave as is"."""

    name: str | None = None
    type: PartnerType | None = None
    status: PartnerStatus | None = None
    website: str | None = None
    contact_email: str | None = None
    agreement_signed_on: date | None = None
    notes: str | None = None


def _name_taken(name: str, *, excluding: int | None = None) -> bool:
    return Partner.objects.filter(name__iexact=name).exclude(pk=excluding).exists()


def create_partner(*, actor: User, data: NewPartner, clock: Clock = SYSTEM_CLOCK) -> int:
    require_role(actor, Role.LEAD)
    if _name_taken(data.name):
        raise InvalidInput.for_field("name", "A partner with this name already exists.")
    now = clock.now()
    with transaction.atomic():
        partner = Partner.objects.create(
            name=data.name,
            type=data.type,
            website=data.website,
            contact_email=data.contact_email,
            agreement_signed_on=data.agreement_signed_on,
            notes=data.notes,
            created_at=now,
            updated_at=now,
        )
        record_event(
            type=EventType.PARTNER_CREATED,
            entity=EntityType.PARTNER,
            entity_id=partner.pk,
            payload=PartnerCreatedPayload(partner_id=partner.pk, name=partner.name, type=data.type),
            actor=actor,
            at=now,
        )
    return partner.pk


def update_partner(*, actor: User, partner_id: int, changes: PartnerChanges, clock: Clock = SYSTEM_CLOCK) -> None:
    require_role(actor, Role.LEAD)
    now = clock.now()
    with transaction.atomic():
        partner = Partner.objects.select_for_update().filter(pk=partner_id).first()
        if partner is None:
            raise NotFound.entity("partner", partner_id)
        if changes.name is not None and _name_taken(changes.name, excluding=partner.pk):
            raise InvalidInput.for_field("name", "A partner with this name already exists.")
        diffs: list[FieldChange] = []
        for field in ("name", "type", "status", "website", "contact_email", "agreement_signed_on", "notes"):
            new = getattr(changes, field)
            old = getattr(partner, field)
            if new is None or new == old:
                continue
            diffs.append(
                FieldChange(
                    field=field,
                    before=old.isoformat() if isinstance(old, date) else old,
                    after=new.isoformat() if isinstance(new, date) else str(new),
                )
            )
            setattr(partner, field, new)
        if not diffs:
            return
        partner.updated_at = now
        partner.save()
        record_event(
            type=EventType.PARTNER_UPDATED,
            entity=EntityType.PARTNER,
            entity_id=partner.pk,
            payload=PartnerUpdatedPayload(partner_id=partner.pk, changes=tuple(diffs)),
            actor=actor,
            at=now,
        )
