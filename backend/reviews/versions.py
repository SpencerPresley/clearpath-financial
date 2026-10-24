"""New versions of an item: resubmission, a new round, and the shared `create_version` (reviewer edits here,
fast-track versions in workstream F). Versions are immutable; every change of copy is v+1."""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max

from accounts.models import User
from audit.payloads import ItemNewRoundStartedPayload, ItemResubmittedPayload, VersionCreatedPayload
from audit.services import record_event
from checks.services import PersistedChecks, run_code_checks
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import CheckStatus, EntityType, EventType, VersionOrigin
from core.errors import NotPermitted
from reviews.assignment import auto_assign, locked_item
from reviews.models import ReviewItem, Version
from reviews.transitions import Action, apply_transition, require_transition


@dataclass(frozen=True)
class CreatedVersion:
    version: Version
    checks: PersistedChecks


@dataclass(frozen=True)
class VersionResult:
    item_id: int
    version_id: int
    version_n: int
    round: int
    event_id: int


def _insert_version(
    item: ReviewItem, *, text: str, author: User, origin: VersionOrigin, based_on: Version | None, clock: Clock
) -> Version:
    """v+1 becomes current. The AI check status follows the origin (spec §4.2 ruling 4): a submission waits for
    a fresh AI check; a fast-track version skips it; a reviewer edit carries its base version's result (the
    decision records `ai_review_carried_from`)."""
    now = clock.now()
    n = (Version.objects.filter(item=item).aggregate(n=Max("n"))["n"] or 0) + 1
    version = Version.objects.create(
        item=item,
        n=n,
        content_text=text,
        content_sha256=Version.hash_content(text),
        author=author,
        origin=origin,
        based_on=based_on,
        created_at=now,
    )
    item.current_version = version
    if origin is VersionOrigin.SUBMISSION:
        item.llm_check_status = CheckStatus.PENDING
    elif origin is VersionOrigin.FAST_TRACK:
        item.llm_check_status = CheckStatus.SKIPPED
    item.updated_at = now
    item.save(update_fields=["current_version", "llm_check_status", "updated_at"])
    return version


def _check(item: ReviewItem, version: Version, clock: Clock) -> PersistedChecks:
    checks = run_code_checks(version=version, clock=clock)
    item.open_findings_count = checks.open_findings_count
    item.save(update_fields=["open_findings_count"])
    return checks


def create_version(  # what a version is made of
    *,
    item: ReviewItem,
    text: str,
    author: User,
    origin: VersionOrigin,
    clock: Clock = SYSTEM_CLOCK,
    based_on: Version | None = None,
) -> CreatedVersion:
    """Add v+1 to `item` (locked by the caller, inside its transaction) without changing its status: run the code
    checks synchronously and write `open_findings_count`. Records VERSION_CREATED for reviewer-edit and
    fast-track versions; a submission version is recorded by its action's event (submit, resubmit, new round)."""
    version = _insert_version(item, text=text, author=author, origin=origin, based_on=based_on, clock=clock)
    if origin is not VersionOrigin.SUBMISSION:
        record_event(
            type=EventType.VERSION_CREATED,
            entity=EntityType.VERSION,
            entity_id=version.pk,
            item_id=item.pk,
            payload=VersionCreatedPayload(
                version_id=version.pk,
                version_n=version.n,
                origin=origin,
                based_on_version_id=based_on.pk if based_on is not None else None,
            ),
            actor=author,
            at=clock.now(),
        )
    return CreatedVersion(version=version, checks=_check(item, version, clock))


def _require_owner(actor: User, item: ReviewItem) -> None:
    if item.owner_id != actor.pk:  # pyrefly: ignore[missing-attribute]
        raise NotPermitted("Only the submitter can submit a new version.")


def _next_round(
    *, actor: User, item_id: int, text: str | None, action: Action, note: str, clock: Clock
) -> VersionResult:
    now = clock.now()
    with transaction.atomic():
        item = locked_item(item_id)
        _require_owner(actor, item)
        require_transition(item, action)
        previous = item.current_version
        content = text if text is not None else (previous.content_text if previous is not None else "")
        version = _insert_version(
            item, text=content, author=actor, origin=VersionOrigin.SUBMISSION, based_on=previous, clock=clock
        )
        item.round += 1
        item.submitted_at = now
        item.save(update_fields=["round", "submitted_at"])
        if action is Action.RESUBMIT:
            payload = ItemResubmittedPayload(
                version_id=version.pk,
                version_n=version.n,
                round=item.round,
                previous_version_id=previous.pk if previous is not None else 0,
                note=note,
            )
        else:
            payload = ItemNewRoundStartedPayload(version_id=version.pk, version_n=version.n, round=item.round)
        event = apply_transition(item, action, actor=actor, at=now, payload=payload)
        _check(item, version, clock)
        auto_assign(item=item, actor=actor, clock=clock, sticky=True)
    return VersionResult(
        item_id=item.pk, version_id=version.pk, version_n=version.n, round=item.round, event_id=event.pk
    )


def resubmit_item(
    *, actor: User, item_id: int, content_text: str, note: str = "", clock: Clock = SYSTEM_CLOCK
) -> VersionResult:
    """changes_requested -> submitted with v+1 and round + 1, back to the previous reviewer (sticky)."""
    return _next_round(actor=actor, item_id=item_id, text=content_text, action=Action.RESUBMIT, note=note, clock=clock)


def start_new_round(
    *, actor: User, item_id: int, content_text: str | None = None, clock: Clock = SYSTEM_CLOCK
) -> VersionResult:
    """withdrawn | expired -> submitted with v+1 and round + 1 (product-spec: "withdrawn -> draft v+1 ->
    submitted"; the draft is never stored). Without `content_text`, v+1 copies the current version, which after
    a terms change is the generated fast-track version. Clears `reopen_reason`."""
    return _next_round(actor=actor, item_id=item_id, text=content_text, action=Action.NEW_ROUND, note="", clock=clock)
