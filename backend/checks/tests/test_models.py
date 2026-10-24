from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange

from accounts.models import User
from checks.models import Finding, TermsRef
from core.db import constraint_name
from core.domain import FindingSource, FindingState, PersonalLoanTerms, Severity, TermsField
from reviews.models import Version
from reviews.tests.factories import AT, make_item, make_version
from terms.models import OfferTerms


@pytest.fixture
def version(marketer: User) -> Version:
    return make_version(make_item(marketer), "Rates as low as 7.49% APR.")


def _finding(version: Version, **overrides: Any) -> Finding:
    fields: dict[str, Any] = {
        "version": version,
        "rule_id": "reg_z.as_low_as",
        "citation": "Reg Z 1026.24(a)",
        "source": FindingSource.CODE,
        "severity": Severity.BLOCKING,
        "span_start": 6,
        "span_end": 17,
        "quote": "as low as 7",
        "message": "Rate claim may need the full APR range",
        "created_at": AT,
    }
    fields.update(overrides)
    return Finding.objects.create(**fields)


def _violates(name: str, **overrides: Any) -> None:
    version = overrides.pop("version")
    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        _finding(version, **overrides)
    assert constraint_name(caught.value) == name


@pytest.mark.django_db
def test_finding_defaults_to_open(version: Version) -> None:
    assert _finding(version).state == FindingState.OPEN


@pytest.mark.django_db
def test_finding_span_must_be_ordered(version: Version) -> None:
    _violates("finding_span_valid", version=version, span_start=10, span_end=10)


@pytest.mark.django_db
def test_finding_quote_iff_span(version: Version) -> None:
    _violates("finding_quote_iff_span", version=version, quote=None)
    _violates("finding_quote_iff_span", version=version, span_start=None, span_end=None)


@pytest.mark.django_db
def test_human_checklist_finding_has_no_span(version: Version) -> None:
    finding = _finding(
        version, source=FindingSource.HUMAN, rule_id="reg_b.imagery", span_start=None, span_end=None, quote=None
    )

    assert finding.span_start is None


@pytest.mark.django_db
def test_dismissed_finding_needs_reason_and_resolver(version: Version, reviewer: User) -> None:
    _violates(
        "finding_dismissal_has_reason",
        version=version,
        state=FindingState.DISMISSED,
        reason="",
        resolved_by=reviewer,
        resolved_at=AT,
    )
    _violates("finding_resolution_recorded", version=version, state=FindingState.ACCEPTED, reason="")


@pytest.mark.django_db
def test_carried_finding_must_be_dismissed(version: Version, reviewer: User) -> None:
    original = _finding(
        version,
        state=FindingState.DISMISSED,
        reason="Qualifier is in the footer.",
        resolved_by=reviewer,
        resolved_at=AT,
    )

    _violates("finding_carried_is_dismissed", version=version, rule_id="other", carried_from=original)


@pytest.mark.django_db
def test_finding_unique_per_version_rule_span(version: Version) -> None:
    _finding(version)
    _violates("finding_unique_per_version_rule_span", version=version)


@pytest.mark.django_db
def test_human_findings_with_null_spans_collide(version: Version) -> None:
    human = {
        "source": FindingSource.HUMAN,
        "rule_id": "reg_b.imagery",
        "span_start": None,
        "span_end": None,
        "quote": None,
    }
    _finding(version, **human)

    _violates("finding_unique_per_version_rule_span", version=version, **human)


@pytest.mark.django_db
def test_terms_ref_span_check(version: Version, lead: User) -> None:
    terms = OfferTerms.objects.create(
        product="personal_loan",
        version=1,
        effective_range=DateTimeTZRange(datetime(2026, 1, 1, tzinfo=UTC), None, "[)"),
        values=PersonalLoanTerms(
            apr_min=Decimal("7.49"),
            apr_max=Decimal("35.99"),
            amount_min=Decimal(1000),
            amount_max=Decimal(50000),
            term_months=(36,),
            origination_fee_min_pct=Decimal(0),
            origination_fee_max_pct=Decimal(8),
        ).model_dump(mode="json"),
        created_by=lead,
        created_at=AT,
    )
    TermsRef.objects.create(
        version=version,
        offer_terms=terms,
        field=TermsField.APR_MIN,
        span_start=16,
        span_end=21,
        quote="7.49%",
        quoted_value=Decimal("7.49"),
    )

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        TermsRef.objects.create(
            version=version,
            offer_terms=terms,
            field=TermsField.APR_MAX,
            span_start=21,
            span_end=16,
            quote="x",
            quoted_value=Decimal(1),
        )
    assert constraint_name(caught.value) == "terms_ref_span_valid"
