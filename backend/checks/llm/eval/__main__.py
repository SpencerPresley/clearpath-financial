"""Live eval: `uv run python -m checks.llm.eval [--repeat N] [--case NAME ...] [--model NAME]` from backend/.

It calls the real model and needs `ANTHROPIC_API_KEY` in the process environment. Nothing here reads `.env`.
It prints, per rule, the precision and recall over the corpus, plus drops, re-anchors, tokens and cost. The pass
rate is reported, not asserted (spec §6.3). Haiku 5.5 takes no temperature, so `--repeat` is how to see
variance.
"""

import argparse
import os
import sys
from decimal import Decimal

from checks.llm.client import DEFAULT_MODEL, get_review_model
from checks.llm.eval.corpus import CASES
from checks.llm.eval.runner import render, run_eval
from core.domain import CreditCardTerms, PersonalLoanTerms, Product

# Same values as the engine's test fixtures (checks/engine/tests/conftest.py), so code findings match the corpus.
PL_TERMS = PersonalLoanTerms(
    apr_min=Decimal("7.49"),
    apr_max=Decimal("35.99"),
    amount_min=Decimal(1000),
    amount_max=Decimal(50000),
    term_months=(24, 36, 48, 60),
    origination_fee_min_pct=Decimal(0),
    origination_fee_max_pct=Decimal(8),
)
CC_TERMS = CreditCardTerms(
    purchase_apr_min=Decimal("19.99"),
    purchase_apr_max=Decimal("29.99"),
    purchase_apr_variable=True,
    intro_apr=Decimal(0),
    intro_months=15,
    balance_transfer_fee_pct=Decimal(3),
    annual_fee=Decimal(0),
    issuing_bank="Lakeside Bank",
)


def demo_terms(product: Product) -> PersonalLoanTerms | CreditCardTerms | None:
    return {Product.PERSONAL_LOAN: PL_TERMS, Product.CREDIT_CARD: CC_TERMS}.get(product)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m checks.llm.eval", description=__doc__)
    parser.add_argument("--repeat", type=int, default=1, help="run the corpus N times (no temperature on Haiku 5.5)")
    parser.add_argument("--case", action="append", default=[], help="only these case names (repeatable)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write("ANTHROPIC_API_KEY is not set in the environment.\n")
        return 2
    cases = [c for c in CASES if not args.case or c.name in args.case]
    if not cases:
        sys.stderr.write(f"No cases match {args.case}.\n")
        return 2
    runs = run_eval(cases, model=get_review_model(args.model), terms=demo_terms, repeat=args.repeat)
    sys.stdout.write(f"model {args.model}, {len(cases)} cases x {args.repeat}\n\n{render(runs)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
