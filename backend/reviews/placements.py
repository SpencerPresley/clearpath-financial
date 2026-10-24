"""Placements: where approved content runs and when (spec §4.2 ruling 2), takedowns, and retention dates.

The marketer records placements after approval. An item is live while it has a placement with
`first_run <= today <= (last_run or forever)` and no confirmed takedown (`selectors.live_placements_q`).
"""

from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction

from accounts.models import User
from audit.payloads import FieldChange, PlacementRecordedPayload, PlacementUpdatedPayload, TakedownConfirmedPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EntityType, EventType, ItemStatus, Role, TakedownState
from core.errors import Conflict, InvalidInput, InvalidTransition, NotFound, NotPermitted
from core.permissions import has_role
from reviews.assignment import locked_item
from reviews.models import APPROVED_OUTCOMES, Decision, Placement, ReviewItem
from reviews.months import add_months

# Reg N 12 CFR 1014.5: 24 months from the last date the ad ran. Prescreened offers keep 3 years (FCRA
# 1681m(d)(3)), which also covers Reg B's 25 months (decisions.md "Two kinds of file").
RETENTION_MONTHS: Final = 24
PRESCREEN_RETENTION_MONTHS: Final = 36

type Keep = Literal["keep"]


@dataclass(frozen=True)
class PlacementInput:
    location: str
    first_run: date
    url: str | None = None
    last_run: date | None = None
    monitored: bool = False


@dataclass(frozen=True)
class PlacementChanges:
    """ "keep" leaves a field as it is; `last_run=None` makes the placement open-ended."""

    last_run: date | Keep | None = "keep"
    monitored: bool | Keep = "keep"


def _require_placement_editor(actor: User, item: ReviewItem) -> None:
    if item.owner_id != actor.pk and not has_role(actor, Role.LEAD, Role.ADMIN):  # pyrefly: ignore[missing-attribute]
        raise NotPermitted("Only the submitter or a lead can record placements.")


def _end(placement: Placement) -> date | None:
    """The last day this placement ran, or None while it may still run."""
    confirmed = placement.takedown_state == TakedownState.CONFIRMED and placement.takedown_confirmed_at is not None
    if confirmed and placement.takedown_confirmed_at is not None:
        taken_down = placement.takedown_confirmed_at.date()
        return min(placement.last_run, taken_down) if placement.last_run else taken_down
    return placement.last_run


def update_retention(item: ReviewItem) -> None:
    """`retention_until` = the last run date + 24 months (36 for prescreen); None while any placement is open."""
    ends = [_end(p) for p in Placement.objects.filter(item=item)]
    if not ends or any(e is None for e in ends):
        retention = None
    else:
        last = max(e for e in ends if e is not None)
        retention = add_months(last, PRESCREEN_RETENTION_MONTHS if item.is_prescreen else RETENTION_MONTHS)
    if retention != item.retention_until:
        item.retention_until = retention
        item.save(update_fields=["retention_until"])


def _validate(first_run: date, last_run: date | None, url: str | None) -> None:
    if last_run is not None and last_run < first_run:
        raise InvalidInput.for_field("last_run", "The last run date is before the first run date.")
    if url:
        try:
            URLValidator(schemes=["http", "https"])(url)
        except ValidationError as exc:
            raise InvalidInput.for_field("url", "Enter a web address starting with http:// or https://.") from exc


def record_placement(*, actor: User, item_id: int, data: PlacementInput, clock: Clock = SYSTEM_CLOCK) -> int:
    """Record where the approved version runs. Only on an approved item; the placement is of the version its
    latest approval covers."""
    _validate(data.first_run, data.last_run, data.url)
    now = clock.now()
    with transaction.atomic():
        item = locked_item(item_id)
        _require_placement_editor(actor, item)
        status = ItemStatus(item.status)
        if status is not ItemStatus.APPROVED:
            raise InvalidTransition(action="record_placement", from_status=status)
        approval = (
            Decision.objects.filter(item=item, outcome__in=APPROVED_OUTCOMES)
            .select_related("version")
            .order_by("-decided_at", "-pk")
            .first()
        )
        if approval is None:  # an approved legacy item: imported without versions
            raise Conflict("This item has no approved version to place.")
        placement = Placement.objects.create(
            item=item,
            approved_version=approval.version,
            location=data.location.strip(),
            url=data.url or "",
            first_run=data.first_run,
            last_run=data.last_run,
            monitored=data.monitored,
            created_by=actor,
            created_at=now,
        )
        record_event(
            type=EventType.PLACEMENT_RECORDED,
            entity=EntityType.PLACEMENT,
            entity_id=placement.pk,
            item_id=item.pk,
            payload=PlacementRecordedPayload(
                placement_id=placement.pk,
                version_id=approval.version.pk,
                location=placement.location,
                first_run=placement.first_run,
                last_run=placement.last_run,
            ),
            actor=actor,
            at=now,
        )
        update_retention(item)
    return placement.pk


def _locked_placement(placement_id: int) -> tuple[Placement, ReviewItem]:
    found = Placement.objects.filter(pk=placement_id).values_list("item_id", flat=True).first()
    if found is None:
        raise NotFound.entity("placement", placement_id)
    item = locked_item(found)
    return Placement.objects.select_for_update().get(pk=placement_id), item


def update_placement(*, actor: User, placement_id: int, changes: PlacementChanges, clock: Clock = SYSTEM_CLOCK) -> None:
    """Change the last run date (end a run, or extend it) or the monitored flag."""
    now = clock.now()
    with transaction.atomic():
        placement, item = _locked_placement(placement_id)
        _require_placement_editor(actor, item)
        diffs: list[FieldChange] = []
        if not isinstance(changes.last_run, str) and changes.last_run != placement.last_run:  # str: "keep"
            _validate(placement.first_run, changes.last_run, None)
            diffs.append(
                FieldChange(
                    field="last_run",
                    before=placement.last_run.isoformat() if placement.last_run else None,
                    after=changes.last_run.isoformat() if changes.last_run else None,
                )
            )
            placement.last_run = changes.last_run
        if isinstance(changes.monitored, bool) and changes.monitored != placement.monitored:
            diffs.append(FieldChange(field="monitored", before=placement.monitored, after=changes.monitored))
            placement.monitored = changes.monitored
        if not diffs:
            return
        placement.save(update_fields=["last_run", "monitored"])
        record_event(
            type=EventType.PLACEMENT_UPDATED,
            entity=EntityType.PLACEMENT,
            entity_id=placement.pk,
            item_id=item.pk,
            payload=PlacementUpdatedPayload(placement_id=placement.pk, changes=tuple(diffs)),
            actor=actor,
            at=now,
        )
        update_retention(item)


def confirm_takedown(*, actor: User, placement_id: int, clock: Clock = SYSTEM_CLOCK) -> None:
    """The requested takedown happened: the placement stops being live, and "time to fix live content" stops."""
    now = clock.now()
    with transaction.atomic():
        placement, item = _locked_placement(placement_id)
        if item.owner_id != actor.pk and not has_role(actor, Role.REVIEWER, Role.ADMIN):  # pyrefly: ignore[missing-attribute]
            raise NotPermitted("Only the submitter or a reviewer can confirm a takedown.")
        if placement.takedown_state != TakedownState.REQUESTED:
            raise Conflict(
                "No takedown was requested for this placement.", details={"takedown_state": placement.takedown_state}
            )
        placement.takedown_state = TakedownState.CONFIRMED
        placement.takedown_confirmed_at = now
        placement.save(update_fields=["takedown_state", "takedown_confirmed_at"])
        record_event(
            type=EventType.TAKEDOWN_CONFIRMED,
            entity=EntityType.PLACEMENT,
            entity_id=placement.pk,
            item_id=item.pk,
            payload=TakedownConfirmedPayload(placement_id=placement.pk),
            actor=actor,
            at=now,
        )
        update_retention(item)
