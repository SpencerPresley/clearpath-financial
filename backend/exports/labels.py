"""Readable labels for exported files. Status labels are the UI's (frontend/src/ui/badges.tsx STATUS_META), so a
spreadsheet says "Re-review" where the queue does (spec §5.4: one term per concept)."""

from collections.abc import Mapping
from typing import Final

from core.domain import Channel, DecisionLane, DecisionOutcome, ItemStatus, Product, RiskTier

STATUS_LABELS: Final[Mapping[ItemStatus, str]] = {
    ItemStatus.DRAFT: "Draft",
    ItemStatus.SUBMITTED: "Submitted",
    ItemStatus.IN_REVIEW: "In review",
    ItemStatus.CHANGES_REQUESTED: "Changes requested",
    ItemStatus.APPROVED: "Approved",
    ItemStatus.REJECTED: "Rejected",
    ItemStatus.NEEDS_REREVIEW: "Re-review",
    ItemStatus.EXPIRED: "Expired",
    ItemStatus.WITHDRAWN: "Withdrawn",
}

# The glossary's Decision names (spec §5.4).
OUTCOME_LABELS: Final[Mapping[DecisionOutcome, str]] = {
    DecisionOutcome.APPROVED: "Approve",
    DecisionOutcome.APPROVED_WITH_EDITS: "Approve with edits",
    DecisionOutcome.CHANGES_REQUESTED: "Request changes",
    DecisionOutcome.REJECTED: "Reject",
}

LANE_LABELS: Final[Mapping[DecisionLane, str]] = {
    DecisionLane.STANDARD: "Standard review",
    DecisionLane.FAST_TRACK: "Fast-track (offer terms changed)",
    DecisionLane.REAFFIRM: "Reaffirmed",
}

PRODUCT_LABELS: Final[Mapping[Product, str]] = {
    Product.PERSONAL_LOAN: "Personal loan",
    Product.CREDIT_CARD: "Credit card",
    Product.MORTGAGE_PREQUAL: "Mortgage prequal",
}

CHANNEL_LABELS: Final[Mapping[Channel, str]] = {
    Channel.EMAIL: "Email",
    Channel.SMS: "SMS",
    Channel.PAID_SOCIAL: "Paid social",
    Channel.PAID_SEARCH: "Paid search",
    Channel.DISPLAY: "Display",
    Channel.DIRECT_MAIL: "Direct mail",
    Channel.LANDING_PAGE: "Landing page",
    Channel.AFFILIATE_PAGE: "Affiliate page",
    Channel.CALL_SCRIPT: "Call script",
}

RISK_LABELS: Final[Mapping[RiskTier, str]] = {RiskTier.HIGH: "High", RiskTier.MEDIUM: "Medium", RiskTier.LOW: "Low"}
