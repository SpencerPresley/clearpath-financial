"""What workstream C's engine emits must fit what `checks` persists and serves.

The engine (`checks.engine`, owned by C) is pure Python with its own frozen types; `checks.services` stores its
output in Finding/TermsRef and the API serves TermsRef.field as `TermsField`. These tests fail if either side
drifts: a new terms claim the enum doesn't know would 500 on serialization, and a long rule id or citation
would fail the insert.
"""

import pytest
from django.db import models

from checks.engine import RULES, CheckResult, RuleContext, run_code_checks
from checks.engine.tests.conftest import TODAY, cc_terms, pl_terms
from checks.engine.tests.samples import SAMPLES, Sample
from checks.models import Finding, TermsRef
from core.domain import Product, TermsField


def _check(sample: Sample) -> CheckResult:
    terms = {Product.PERSONAL_LOAN: pl_terms(), Product.CREDIT_CARD: cc_terms()}.get(sample.product)
    return run_code_checks(
        RuleContext(
            text=sample.text,
            product=sample.product,
            channel=sample.channel,
            markets=frozenset(sample.markets),
            partner_type=sample.partner_type,
            attachment_kinds=frozenset(sample.attachments),
            terms=terms,
            today=TODAY,
        )
    )


def _max_length(model: type[Finding | TermsRef], name: str) -> int:
    field = model._meta.get_field(name)
    assert isinstance(field, models.CharField)
    assert field.max_length is not None
    return field.max_length


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_every_terms_claim_the_engine_emits_is_a_terms_field(sample: Sample) -> None:
    fields = {ref.field for ref in _check(sample).terms_refs}

    assert fields <= {f.value for f in TermsField}
    assert all(len(f) <= _max_length(TermsRef, "field") for f in fields)


def test_the_sample_corpus_exercises_terms_claims() -> None:
    # Guards the test above against passing vacuously.
    assert sum(len(_check(s).terms_refs) for s in SAMPLES) > 0


def test_every_rule_fits_the_finding_columns() -> None:
    too_long = [
        spec.id
        for spec in RULES.values()
        if len(spec.id) > _max_length(Finding, "rule_id") or len(spec.citation) > _max_length(Finding, "citation")
    ]

    assert too_long == []
