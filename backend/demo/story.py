"""The demo seed's vocabulary: people, partners, offer terms, and item stories told as timed steps.

Nothing here touches the database. `demo.runner` turns each step into the service call a real person would have
made at that moment (a `FixedClock` set to the step's instant), so every row the seed leaves behind was written
by the service that owns it, with its event.

Times are relative to the moment the seed runs, so "waiting more than 3 days" and the metrics stay meaningful
whenever the demo is reset: `day(12, "09:40")` is 09:40 Pacific twelve days before the seed date, `ago(5)` is
five minutes before the seed ran. Run dates (`first_run`, `last_run`) are whole days relative to the seed date:
-52 is 52 days ago, 30 is a month from now.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from core.domain import (
    AttachmentKind,
    Channel,
    CreditCardTerms,
    DecisionOutcome,
    DriftResult,
    ItemStatus,
    Market,
    PartnerType,
    PersonalLoanTerms,
    Product,
    ReopenReason,
    RiskTier,
    Role,
)

# ClearPath's compliance team sits in San Francisco; business hours are Pacific.
LOCAL_TZ: Final = ZoneInfo("America/Los_Angeles")


@dataclass(frozen=True)
class When:
    """A backdated instant. Exactly one of: `days` before the seed date at local `hhmm`; `minutes_ago`; `on` an
    absolute date at local `hhmm` (offer terms that predate the demo window)."""

    days: int | None = None
    hhmm: str = "09:00"
    minutes_ago: int | None = None
    on: date | None = None

    def resolve(self, now: datetime) -> datetime:
        if self.minutes_ago is not None:
            return now - timedelta(minutes=self.minutes_ago)
        hour, minute = (int(part) for part in self.hhmm.split(":"))
        local_day = self.on or now.astimezone(LOCAL_TZ).date() - timedelta(days=self.days or 0)
        return datetime.combine(local_day, time(hour, minute), tzinfo=LOCAL_TZ).astimezone(UTC)


def day(days: int, hhmm: str = "09:00") -> When:
    return When(days=days, hhmm=hhmm)


def ago(minutes: int) -> When:
    return When(minutes_ago=minutes)


def on(when: date, hhmm: str = "09:00") -> When:
    return When(on=when, hhmm=hhmm)


# --- people, partners, terms -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    key: str
    email: str
    name: str
    roles: tuple[Role, ...]
    team: str  # business unit, for the docs


@dataclass(frozen=True)
class PartnerSpec:
    key: str
    name: str
    type: PartnerType
    website: str
    contact_email: str
    agreement_signed_on: date
    notes: str
    agreement: str  # the agreement's text, stored as a .txt attachment


@dataclass(frozen=True)
class TermsSpec:
    product: Product
    at: When
    values: PersonalLoanTerms | CreditCardTerms
    note: str


# --- the AI pre-review, scripted ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class AiFinding:
    """What the scripted model reports. `quote` must appear in the version text; its first occurrence is used."""

    rule_id: str
    quote: str
    message: str
    suggested_fix: str = ""


@dataclass(frozen=True)
class AiResult:
    findings: tuple[AiFinding, ...] = ()


@dataclass(frozen=True)
class AiOutage:
    """The provider is overloaded on every attempt: the check retries, then ends failed (Approve needs an override)."""


@dataclass(frozen=True)
class AiPending:
    """The check is requested and left pending (the most recent submission); the reconciler picks it up later."""


type AiScript = AiResult | AiOutage | AiPending

CLEAN: Final = AiResult()


# --- item steps --------------------------------------------------------------------------------------------------
# `by=None` means "whoever the item is assigned to" for review actions, and the owner for marketer actions.


@dataclass(frozen=True)
class Submit:
    at: When
    ai: AiScript = CLEAN


@dataclass(frozen=True)
class Resubmit:
    at: When
    text: int  # index into Story.versions
    note: str = ""
    ai: AiScript = CLEAN


@dataclass(frozen=True)
class NewRound:
    at: When
    text: int | None = None  # None: start from the current version (after a terms change, the generated one)
    ai: AiScript = CLEAN


@dataclass(frozen=True)
class Claim:
    at: When
    by: str | None = None


@dataclass(frozen=True)
class Assign:
    at: When
    to: str | None  # None: back to the pool
    reason: str
    by: str = "rachel"


@dataclass(frozen=True)
class Accept:
    at: When
    rule: str
    note: str = ""
    quote: str | None = None  # narrows to one finding when the rule fired more than once
    by: str | None = None


@dataclass(frozen=True)
class Dismiss:
    at: When
    rule: str
    reason: str
    quote: str | None = None
    by: str | None = None


@dataclass(frozen=True)
class Checklist:
    """Dismiss every open human checklist item on the current version with the reviewer's usual notes."""

    at: When
    by: str | None = None
    notes: tuple[tuple[str, str], ...] = ()  # (rule id, reason) overrides


@dataclass(frozen=True)
class Comment:
    at: When
    body: str
    by: str | None = None  # None: the assignee
    mentions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decide:
    at: When
    outcome: DecisionOutcome
    reason: str
    by: str | None = None
    edited: int | None = None  # approve with edits: index into Story.versions
    override: str | None = None  # the AI check failed
    needs_triage: bool = False  # approve with edits whose v+1 raises findings (two-phase)


@dataclass(frozen=True)
class EditFields:
    at: When
    by: str | None = None
    notes: str | None = None
    tags: tuple[str, ...] | None = None
    risk_tier: RiskTier | None = None


@dataclass(frozen=True)
class Place:
    at: When
    location: str
    first_run: int
    last_run: int | None = None
    url: str = ""
    monitored: bool = False


@dataclass(frozen=True)
class Pull:
    at: When
    reason: str
    by: str | None = None


@dataclass(frozen=True)
class ConfirmTakedown:
    at: When


@dataclass(frozen=True)
class Reaffirm:
    at: When
    reason: str
    by: str | None = None
    finds_new: bool = False  # the re-run checks raise findings, so this attempt is refused until they're triaged


@dataclass(frozen=True)
class FastTrack:
    at: When
    reason: str
    by: str | None = None


@dataclass(frozen=True)
class OnDemoPage:
    """A monitored placement on one of the partner pages ClearPath hosts for the demo (`drift.demo.PAGES`), live
    from this day. The story's approved copy is the page's copy."""

    at: When
    slug: str
    by: str | None = None


@dataclass(frozen=True)
class PartnerEdit:
    """The partner publishes the demo page's edited variant (what "Simulate partner edit" does). The page stays
    edited after the seed, so a check run later finds what the seeded check found."""

    at: When


@dataclass(frozen=True)
class PageCheck:
    """The drift monitor checks the story's demo page, through the drift services, on the HTML the page serves."""

    at: When
    expect: DriftResult


@dataclass(frozen=True)
class Attach:
    at: When
    kind: AttachmentKind
    name: str
    body: str
    by: str | None = None


type Step = (
    Submit
    | Resubmit
    | NewRound
    | Claim
    | Assign
    | Accept
    | Dismiss
    | Checklist
    | Comment
    | Decide
    | EditFields
    | Place
    | Pull
    | ConfirmTakedown
    | Reaffirm
    | FastTrack
    | OnDemoPage
    | PartnerEdit
    | PageCheck
    | Attach
)


@dataclass(frozen=True)
class Story:
    """One review item from submission to where it stands today."""

    key: str
    owner: str
    title: str
    product: Product
    channel: Channel
    versions: tuple[str, ...]
    steps: tuple[Step, ...]
    expect: ItemStatus  # where the story ends; the runner checks it
    markets: tuple[Market, ...] = (Market.NATIONAL,)
    partner: str | None = None
    prescreen: bool = False
    tags: tuple[str, ...] = ()
    first_run: int = 0
    last_run: int | None = None
    expect_reason: ReopenReason | None = None


# --- team-wide steps ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SetAvailability:
    at: When
    who: str
    available: bool


@dataclass(frozen=True)
class ImportTracker:
    """`at` is where the import replays (it sets the legacy items' keys); `dated` is the time it records, when the
    story puts it earlier than its replay slot."""

    at: When
    by: str = "admin"
    dated: When | None = None


@dataclass(frozen=True)
class ReleaseQueue:
    """`who` is out: a lead returns their unstarted items to the pool and hands what they'd started to `cover`."""

    at: When
    who: str
    reason: str
    cover: str
    cover_reason: str
    by: str = "rachel"


type GlobalStep = SetAvailability | ImportTracker | ReleaseQueue


@dataclass(frozen=True)
class Catalog:
    personas: tuple[Persona, ...]
    partners: tuple[PartnerSpec, ...]
    terms: tuple[TermsSpec, ...]
    stories: tuple[Story, ...]
    events: tuple[GlobalStep, ...]
    go_live: When  # the switch from the tracker: nothing native predates it (partners and terms are entered then)
    lead: str = "rachel"
    admin: str = "admin"
