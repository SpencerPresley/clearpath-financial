import pytest

from core.domain import Channel, Product, RiskTier
from reviews.risk import derive_risk_tier


@pytest.mark.parametrize(
    ("product", "channel", "has_partner", "is_prescreen", "expected"),
    [
        # High: affiliate/partner channels, mortgage, prescreen (spec §4.2 ruling 5).
        (Product.PERSONAL_LOAN, Channel.AFFILIATE_PAGE, True, False, RiskTier.HIGH),
        (Product.PERSONAL_LOAN, Channel.EMAIL, True, False, RiskTier.HIGH),  # any partner-published content
        (Product.MORTGAGE_PREQUAL, Channel.EMAIL, False, False, RiskTier.HIGH),
        (Product.CREDIT_CARD, Channel.DIRECT_MAIL, False, True, RiskTier.HIGH),
        # Medium: paid ads and landing pages.
        (Product.PERSONAL_LOAN, Channel.PAID_SOCIAL, False, False, RiskTier.MEDIUM),
        (Product.PERSONAL_LOAN, Channel.PAID_SEARCH, False, False, RiskTier.MEDIUM),
        (Product.CREDIT_CARD, Channel.DISPLAY, False, False, RiskTier.MEDIUM),
        (Product.CREDIT_CARD, Channel.LANDING_PAGE, False, False, RiskTier.MEDIUM),
        # Low: the rest.
        (Product.PERSONAL_LOAN, Channel.EMAIL, False, False, RiskTier.LOW),
        (Product.CREDIT_CARD, Channel.SMS, False, False, RiskTier.LOW),
        (Product.PERSONAL_LOAN, Channel.DIRECT_MAIL, False, False, RiskTier.LOW),
        (Product.PERSONAL_LOAN, Channel.CALL_SCRIPT, False, False, RiskTier.LOW),
    ],
)
def test_derive_risk_tier(
    product: Product, channel: Channel, has_partner: bool, is_prescreen: bool, expected: RiskTier
) -> None:
    assert (
        derive_risk_tier(product=product, channel=channel, has_partner=has_partner, is_prescreen=is_prescreen)
        is expected
    )


def test_every_channel_has_a_tier() -> None:
    for channel in Channel:
        derive_risk_tier(product=Product.PERSONAL_LOAN, channel=channel, has_partner=False, is_prescreen=False)
