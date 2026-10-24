"""Shared domain vocabulary.

Enums and value types used by more than one app (models, the rules engine, the API). One definition per
concept so the same word means the same thing everywhere (spec §5.4 glossary).
"""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Product(StrEnum):
    PERSONAL_LOAN = "personal_loan"
    CREDIT_CARD = "credit_card"
    MORTGAGE_PREQUAL = "mortgage_prequal"


class Channel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PAID_SOCIAL = "paid_social"
    PAID_SEARCH = "paid_search"
    DISPLAY = "display"
    DIRECT_MAIL = "direct_mail"
    LANDING_PAGE = "landing_page"
    AFFILIATE_PAGE = "affiliate_page"
    CALL_SCRIPT = "call_script"


# Channels where a partner publishes on ClearPath's behalf; a partner is required on these.
PARTNER_CHANNELS: frozenset[Channel] = frozenset({Channel.AFFILIATE_PAGE})


class PartnerType(StrEnum):
    AFFILIATE = "affiliate"
    LEAD_GEN = "lead_gen"
    MARKETPLACE = "marketplace"
    INFLUENCER = "influencer"


class Market(StrEnum):
    """Where content is disseminated. Federal rules always apply; state rules key off these."""

    NATIONAL = "national"
    CA = "CA"


class Severity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"


class FindingSource(StrEnum):
    CODE = "code"
    LLM = "llm"
    HUMAN = "human"


class AttachmentKind(StrEnum):
    CREATIVE = "creative"
    SUBSTANTIATION = "substantiation"
    AGREEMENT = "agreement"
    RATE_SHEET = "rate_sheet"
    PRESCREEN_CRITERIA = "prescreen_criteria"
    CONSENT_RECORD = "consent_record"
    SCREENSHOT = "screenshot"
    OTHER = "other"


class RiskTier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Role(StrEnum):
    MARKETER = "marketer"
    REVIEWER = "reviewer"
    LEAD = "lead"
    ADMIN = "admin"


# --- Offer terms -------------------------------------------------------------------------------------------
# Stored as JSONB on OfferTerms.values; validated through these models on every read and write.
# Percentages are APR / fee percents as Decimals (7.49 means 7.49%).


_ZERO = Decimal(0)
_HUNDRED = Decimal(100)

Apr = Annotated[Decimal, Field(gt=_ZERO, lt=_HUNDRED)]
Percent = Annotated[Decimal, Field(ge=_ZERO, lt=_HUNDRED)]
Money = Annotated[Decimal, Field(ge=_ZERO)]
PositiveMoney = Annotated[Decimal, Field(gt=_ZERO)]


class _Terms(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PersonalLoanTerms(_Terms):
    product: Literal[Product.PERSONAL_LOAN] = Product.PERSONAL_LOAN
    apr_min: Apr
    apr_max: Apr
    amount_min: PositiveMoney
    amount_max: PositiveMoney
    term_months: tuple[int, ...] = Field(min_length=1)
    origination_fee_min_pct: Percent
    origination_fee_max_pct: Percent

    @model_validator(mode="after")
    def _ranges_ordered(self) -> Self:
        if self.apr_min > self.apr_max:
            raise ValueError("apr_min must not exceed apr_max")
        if self.amount_min > self.amount_max:
            raise ValueError("amount_min must not exceed amount_max")
        if self.origination_fee_min_pct > self.origination_fee_max_pct:
            raise ValueError("origination_fee_min_pct must not exceed origination_fee_max_pct")
        return self


class CreditCardTerms(_Terms):
    product: Literal[Product.CREDIT_CARD] = Product.CREDIT_CARD
    purchase_apr_min: Apr
    purchase_apr_max: Apr
    purchase_apr_variable: bool = True
    intro_apr: Percent | None = None
    intro_months: int | None = Field(default=None, gt=0)
    balance_transfer_fee_pct: Percent
    annual_fee: Money
    issuing_bank: str = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.purchase_apr_min > self.purchase_apr_max:
            raise ValueError("purchase_apr_min must not exceed purchase_apr_max")
        if (self.intro_apr is None) != (self.intro_months is None):
            raise ValueError("intro_apr and intro_months are set together or not at all")
        return self


# Mortgage prequalification ads quote no standing rate terms; they're checked by rules only.
OfferTermsValues = Annotated[PersonalLoanTerms | CreditCardTerms, Field(discriminator="product")]
