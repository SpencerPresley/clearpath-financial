"""How rules write numbers from the offer terms into messages and suggested fixes.

Every number a suggestion offers comes from the current terms (`RuleContext.terms`) or the copy itself, never a
literal in a rule: a literal goes stale the day the terms change, and the marketer pastes it (walkthrough B2).
"""

from decimal import Decimal

from core.domain import CreditCardTerms, PersonalLoanTerms


def pct(value: Decimal) -> str:
    return f"{value}%"


def money(value: Decimal) -> str:
    return f"${value:,.0f}" if value == value.to_integral_value() else f"${value:,.2f}"


def apr_bounds(terms: PersonalLoanTerms | CreditCardTerms | None) -> tuple[Decimal, Decimal] | None:
    """The APR range on offer: PL APRs, or the card's purchase APRs. None without terms (mortgage prequal)."""
    if isinstance(terms, PersonalLoanTerms):
        return terms.apr_min, terms.apr_max
    if isinstance(terms, CreditCardTerms):
        return terms.purchase_apr_min, terms.purchase_apr_max
    return None


def purchase_apr(terms: CreditCardTerms) -> str:
    """The purchase APR as copy: the range with an en dash, then "variable APR" (or "APR" when fixed); one rate when
    min equals max."""
    low, high = terms.purchase_apr_min, terms.purchase_apr_max
    rates = pct(low) if low == high else f"{pct(low)}\u2013{pct(high)}"
    return f"{rates} {'variable APR' if terms.purchase_apr_variable else 'APR'}"
