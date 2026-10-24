from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from checks.engine import CheckResult, RuleContext
from core.domain import (
    AttachmentKind,
    Channel,
    CreditCardTerms,
    Market,
    PartnerType,
    PersonalLoanTerms,
    Product,
)

TODAY = date(2026, 10, 24)

_UNSET = object()


def pl_terms(**overrides: object) -> PersonalLoanTerms:
    values: dict[str, object] = {
        "apr_min": Decimal("7.49"),
        "apr_max": Decimal("35.99"),
        "amount_min": Decimal(1000),
        "amount_max": Decimal(50000),
        "term_months": (24, 36, 48, 60),
        "origination_fee_min_pct": Decimal(0),
        "origination_fee_max_pct": Decimal(8),
    }
    values.update(overrides)
    return PersonalLoanTerms.model_validate(values)


def cc_terms(**overrides: object) -> CreditCardTerms:
    values: dict[str, object] = {
        "purchase_apr_min": Decimal("19.99"),
        "purchase_apr_max": Decimal("29.99"),
        "purchase_apr_variable": True,
        "intro_apr": Decimal(0),
        "intro_months": 15,
        "balance_transfer_fee_pct": Decimal(3),
        "annual_fee": Decimal(0),
        "issuing_bank": "Lakeside Bank",
    }
    values.update(overrides)
    return CreditCardTerms.model_validate(values)


def make_ctx(  # noqa: PLR0913 - a test builder mirrors RuleContext's fields
    text: str,
    *,
    product: Product = Product.PERSONAL_LOAN,
    channel: Channel = Channel.DISPLAY,
    markets: Iterable[Market] = (Market.NATIONAL,),
    partner_type: PartnerType | None = None,
    attachments: Iterable[AttachmentKind] = (),
    terms: object = _UNSET,
    today: date = TODAY,
) -> RuleContext:
    if terms is _UNSET:
        resolved = {Product.PERSONAL_LOAN: pl_terms(), Product.CREDIT_CARD: cc_terms()}.get(product)
    else:
        assert terms is None or isinstance(terms, PersonalLoanTerms | CreditCardTerms)
        resolved = terms
    return RuleContext(
        text=text,
        product=product,
        channel=channel,
        markets=frozenset(markets),
        partner_type=partner_type,
        attachment_kinds=frozenset(attachments),
        terms=resolved,
        today=today,
    )


def codes(result: CheckResult) -> set[str]:
    return {f.rule_id for f in result.findings}


def quotes(result: CheckResult, rule_id: str) -> list[str | None]:
    return [f.quote for f in result.findings if f.rule_id == rule_id]
