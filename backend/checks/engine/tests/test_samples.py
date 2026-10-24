import pytest

from checks.engine import CheckResult, RuleContext, run_code_checks

from .conftest import TODAY, cc_terms, codes, pl_terms
from .samples import SAMPLES, Sample


def context(sample: Sample, text: str | None = None) -> RuleContext:
    terms = {"personal_loan": pl_terms(), "credit_card": cc_terms()}.get(sample.product)
    return RuleContext(
        text=sample.text if text is None else text,
        product=sample.product,
        channel=sample.channel,
        markets=frozenset(sample.markets),
        partner_type=sample.partner_type,
        attachment_kinds=frozenset(sample.attachments),
        terms=terms,
        today=TODAY,
    )


def check(sample: Sample, text: str | None = None) -> CheckResult:
    return run_code_checks(context(sample, text))


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_sample_findings(sample: Sample) -> None:
    assert codes(check(sample)) == sample.expected
