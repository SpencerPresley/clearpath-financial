"""Risk tier derived at intake (spec §4.2 ruling 5). No manual priority: reviewers and leads may override the
tier inline, which records an event."""

from typing import Final

from core.domain import PARTNER_CHANNELS, Channel, Product, RiskTier

MEDIUM_CHANNELS: Final = frozenset({Channel.PAID_SOCIAL, Channel.PAID_SEARCH, Channel.DISPLAY, Channel.LANDING_PAGE})


def derive_risk_tier(*, product: Product, channel: Channel, has_partner: bool, is_prescreen: bool) -> RiskTier:
    """High: partner-published content (affiliate channels, or any item with a partner), mortgage, prescreen.
    Medium: paid ads and landing pages. Low: everything else (email, SMS, direct mail, call scripts)."""
    if has_partner or channel in PARTNER_CHANNELS or product is Product.MORTGAGE_PREQUAL or is_prescreen:
        return RiskTier.HIGH
    if channel in MEDIUM_CHANNELS:
        return RiskTier.MEDIUM
    return RiskTier.LOW
