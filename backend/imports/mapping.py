"""Column guesses and the value tables the importer normalizes through (samples/README.md, "Every raw value,
mapped"). Pure: no Django.

Two key functions, because the README prescribes two matching rules:
- `value_key`: case- and whitespace-insensitive (status, product, channel, risk tier, Y/N).
- `partner_key`: casefold with spaces and punctuation dropped (`Lend Compare` == `LendCompare`).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from core.domain import Channel, DecisionOutcome, ItemStatus, PartnerStatus, PartnerType, Product, RiskTier
from imports.domain import ImportTargetField

T = ImportTargetField

REQUIRED_TARGETS: Final = (T.LEGACY_REF, T.SUBMITTED_ON, T.TITLE, T.PRODUCT, T.CHANNEL, T.STATUS)

# Readable names for problems and the mapping screen (spec §5.4: one term per concept).
TARGET_LABELS: Final[Mapping[ImportTargetField, str]] = {
    T.LEGACY_REF: "Request ID",
    T.SUBMITTED_ON: "Date submitted",
    T.SUBMITTER: "Submitter",
    T.PRODUCT: "Product",
    T.CHANNEL: "Channel",
    T.TITLE: "Title",
    T.PARTNER: "Partner",
    T.RISK_TIER: "Risk tier",
    T.TRIGGER_TERMS: "Trigger terms",
    T.REVIEWER: "Reviewer",
    T.VERSION_NUMBER: "Version",
    T.ROUNDS: "Rounds",
    T.STATUS: "Status",
    T.COMMENTS: "Comments",
    T.APPROVAL: "Approval date and approver",
    T.EXPIRES_ON: "Approval expires",
    T.PLACEMENT: "Placement",
    T.NOTES: "Notes",
    T.IGNORE: "Ignore",
}

# First match wins, so the order resolves overlaps: "Reviewer Comments" is comments, not reviewer;
# "Approval Expiration" is the expiry, not the approval; "Date Submitted" is not "Submitter".
_GUESSES: Final[tuple[tuple[tuple[str, ...], ImportTargetField], ...]] = (
    (("request id",), T.LEGACY_REF),
    (("legacy ref",), T.LEGACY_REF),
    (("submitted",), T.SUBMITTED_ON),
    (("submitter",), T.SUBMITTER),
    (("comment",), T.COMMENTS),
    (("required changes",), T.COMMENTS),
    (("expir",), T.EXPIRES_ON),
    (("re-review",), T.EXPIRES_ON),
    (("approv",), T.APPROVAL),
    (("product",), T.PRODUCT),
    (("channel",), T.CHANNEL),
    (("asset",), T.TITLE),
    (("title",), T.TITLE),
    (("partner",), T.PARTNER),
    (("affiliate",), T.PARTNER),
    (("risk",), T.RISK_TIER),
    (("trigger",), T.TRIGGER_TERMS),
    (("reviewer",), T.REVIEWER),
    (("version",), T.VERSION_NUMBER),
    (("round",), T.ROUNDS),
    (("status",), T.STATUS),
    (("live url",), T.PLACEMENT),
    (("placement",), T.PLACEMENT),
    (("note",), T.NOTES),
)


def guess_target(header: str) -> ImportTargetField | None:
    h = header.casefold()
    for needles, target in _GUESSES:
        if all(n in h for n in needles):
            return target
    return None


def guess_column_mapping(headers: Iterable[str]) -> dict[str, ImportTargetField]:
    """Every header gets a target; the first header to claim a target keeps it and later ones are ignored."""
    mapping: dict[str, ImportTargetField] = {}
    taken: set[ImportTargetField] = set()
    for header in headers:
        target = guess_target(header)
        if target is None or target in taken:
            mapping[header] = T.IGNORE
        else:
            mapping[header] = target
            taken.add(target)
    return mapping


_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[\W_]+")


def value_key(raw: str) -> str:
    return _WS.sub(" ", raw).strip().casefold()


def partner_key(raw: str) -> str:
    return _NON_ALNUM.sub("", raw.casefold())


@dataclass(frozen=True)
class StatusTarget:
    status: ItemStatus
    outcome: DecisionOutcome | None


_SUBMITTED = StatusTarget(ItemStatus.SUBMITTED, None)
_IN_REVIEW = StatusTarget(ItemStatus.IN_REVIEW, None)
_CHANGES = StatusTarget(ItemStatus.CHANGES_REQUESTED, DecisionOutcome.CHANGES_REQUESTED)
_APPROVED = StatusTarget(ItemStatus.APPROVED, DecisionOutcome.APPROVED)
_WITH_EDITS = StatusTarget(ItemStatus.APPROVED, DecisionOutcome.APPROVED_WITH_EDITS)
_REJECTED = StatusTarget(ItemStatus.REJECTED, DecisionOutcome.REJECTED)

# samples/README.md "Status values" (keys through value_key). Anything else is a preview problem, not a guess.
DEFAULT_STATUS_MAP: Final[Mapping[str, StatusTarget]] = {
    "not started": _SUBMITTED,
    "pending": _SUBMITTED,
    "in review": _IN_REVIEW,
    "changes requested": _CHANGES,
    "changes req.": _CHANGES,
    "needs changes": _CHANGES,
    "approved": _APPROVED,
    "approved w/ changes": _WITH_EDITS,
    "approved - minor edits": _WITH_EDITS,
    "rejected": _REJECTED,
}

# The decision a status implies when the admin maps a status value without naming one.
IMPLIED_OUTCOME: Final[Mapping[ItemStatus, DecisionOutcome | None]] = {
    ItemStatus.APPROVED: DecisionOutcome.APPROVED,
    ItemStatus.REJECTED: DecisionOutcome.REJECTED,
    ItemStatus.CHANGES_REQUESTED: DecisionOutcome.CHANGES_REQUESTED,
}

# Statuses a legacy row may land in: the tracker's workflow. needs_rereview/expired/withdrawn/draft need app
# state (a reopen reason, placements, versions) a tracker row can't supply.
IMPORTABLE_STATUSES: Final = frozenset(
    {
        ItemStatus.SUBMITTED,
        ItemStatus.IN_REVIEW,
        ItemStatus.CHANGES_REQUESTED,
        ItemStatus.APPROVED,
        ItemStatus.REJECTED,
    }
)


def _with_enum_values[E: Product | Channel | RiskTier](labels: Mapping[str, E], enum: Iterable[E]) -> Mapping[str, E]:
    return {**{value_key(e.value): e for e in enum}, **labels}


PRODUCT_MAP: Final[Mapping[str, Product]] = _with_enum_values(
    {
        "pl": Product.PERSONAL_LOAN,
        "personal loan": Product.PERSONAL_LOAN,
        "personal loans": Product.PERSONAL_LOAN,
        "cc": Product.CREDIT_CARD,
        "credit card": Product.CREDIT_CARD,
        "mtg": Product.MORTGAGE_PREQUAL,
        "mortgage prequal": Product.MORTGAGE_PREQUAL,
    },
    Product,
)

CHANNEL_MAP: Final[Mapping[str, Channel]] = _with_enum_values(
    {
        "email": Channel.EMAIL,
        "paid social": Channel.PAID_SOCIAL,
        "paid search": Channel.PAID_SEARCH,
        "direct mail": Channel.DIRECT_MAIL,
        "affiliate page": Channel.AFFILIATE_PAGE,
        "sms": Channel.SMS,
        "landing page": Channel.LANDING_PAGE,
        "call script": Channel.CALL_SCRIPT,
        "display": Channel.DISPLAY,
    },
    Channel,
)

RISK_TIER_MAP: Final[Mapping[str, RiskTier]] = _with_enum_values(
    {"high": RiskTier.HIGH, "medium": RiskTier.MEDIUM, "low": RiskTier.LOW}, RiskTier
)

# Y/yes -> true, N -> false. Blank and "?" are unknown (null, with a warning); never inferred from comments.
TRIGGER_TERMS_MAP: Final[Mapping[str, bool]] = {"y": True, "yes": True, "n": False, "no": False}
TRIGGER_UNKNOWN: Final = frozenset({"?"})

PARTNER_TYPE_MAP: Final[Mapping[str, PartnerType]] = {
    "affiliate": PartnerType.AFFILIATE,
    "lead gen": PartnerType.LEAD_GEN,
    "marketplace": PartnerType.MARKETPLACE,
    "influencer": PartnerType.INFLUENCER,
}

PARTNER_STATUS_MAP: Final[Mapping[str, PartnerStatus]] = {
    "active": PartnerStatus.ACTIVE,
    "paused": PartnerStatus.PAUSED,
    "terminated": PartnerStatus.TERMINATED,
}
