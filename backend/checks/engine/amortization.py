"""Standard amortization for representative examples."""

from decimal import Decimal, localcontext

_MONTHS_PER_YEAR = 12
_HUNDRED = Decimal(100)


def monthly_payment(principal: Decimal, apr: Decimal, months: int) -> Decimal:
    """Level monthly payment for a fully amortizing loan, unrounded. `apr` is a percent (12.99 means 12.99%)."""
    if months <= 0:
        raise ValueError("months must be positive")
    with localcontext() as ctx:
        ctx.prec = 34
        if apr == 0:
            return principal / months
        rate = apr / _HUNDRED / _MONTHS_PER_YEAR
        return principal * rate / (1 - (1 + rate) ** -months)
