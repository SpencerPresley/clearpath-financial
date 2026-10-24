from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from pytest_django import Settings

from accounts.models import User
from checks.models import Finding, TermsRef
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import (
    AttachmentKind,
    DecisionLane,
    DecisionOutcome,
    FindingSource,
    FindingState,
    ItemStatus,
    PersonalLoanTerms,
    Product,
    Role,
    Severity,
    TermsField,
)
from reviews.models import Decision, DecisionEvidence, DecisionTermsVersion, ReviewItem
from reviews.services import AttachmentOwner, add_attachment
from reviews.tests.factories import AT, make_item, make_version
from terms.models import OfferTerms

APPROVED_TEXT = "Personal loans with rates from 7.49% APR. Loans made pursuant to a CFL license."
PL = PersonalLoanTerms(
    apr_min=Decimal("7.49"),
    apr_max=Decimal("35.99"),
    amount_min=Decimal(1000),
    amount_max=Decimal(50000),
    term_months=(24, 36, 60),
    origination_fee_min_pct=Decimal(0),
    origination_fee_max_pct=Decimal(8),
)


@dataclass(frozen=True)
class Approved:
    item: ReviewItem
    decision: Decision
    terms: OfferTerms
    attachment_id: int
    reviewer: User
    marketer: User


@pytest.fixture(autouse=True)
def _media_root(settings: Settings, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def approved(user_factory: UserFactory, marketer: User, clock: FixedClock) -> Approved:
    """An item approved on v2, quoting PL terms v7, with one dismissed finding and one evidence file."""
    reviewer = user_factory(roles=[Role.REVIEWER], display_name="Dana Kim")
    item = make_item(marketer, title="Spring PL email", status=ItemStatus.APPROVED, approved_at=AT)
    make_version(item, "Rates from 6.99% APR.", n=1)
    v2 = make_version(item, APPROVED_TEXT, n=2)
    terms = OfferTerms.objects.create(
        product=Product.PERSONAL_LOAN,
        version=7,
        effective_range=DateTimeTZRange(AT - timedelta(days=30), None, "[)"),
        values=PL.model_dump(mode="json"),
        created_by=reviewer,
        created_at=AT,
    )
    start = APPROVED_TEXT.index("7.49%")
    TermsRef.objects.create(
        version=v2,
        offer_terms=terms,
        field=TermsField.APR_MIN,
        span_start=start,
        span_end=start + 5,
        quote="7.49%",
        quoted_value=Decimal("7.49"),
    )
    Finding.objects.create(
        version=v2,
        rule_id="regz.trigger_terms",
        citation="12 CFR 1026.24(d)",
        source=FindingSource.CODE,
        severity=Severity.WARNING,
        state=FindingState.DISMISSED,
        span_start=start,
        span_end=start + 5,
        quote="7.49%",
        message="Rate claim may need the full APR range.",
        reason="Range is in the footer.",
        resolved_by=reviewer,
        resolved_at=AT,
        created_at=AT,
    )
    ref = add_attachment(
        actor=marketer,
        owner=AttachmentOwner(kind="item", id=item.pk),
        kind=AttachmentKind.RATE_SHEET,
        file=SimpleUploadedFile("rate sheet (Q4).pdf", b"%PDF rate sheet", content_type="application/pdf"),
        clock=clock,
    )
    decision = Decision.objects.create(
        item=item,
        version=v2,
        outcome=DecisionOutcome.APPROVED,
        lane=DecisionLane.STANDARD,
        approver=reviewer,
        reason="Disclosures present.",
        ruleset_date=AT.date(),
        expires_at=AT + timedelta(days=365),
        decided_at=AT,
    )
    DecisionTermsVersion.objects.create(decision=decision, offer_terms=terms)
    DecisionEvidence.objects.create(decision=decision, attachment_id=ref.id, sha256=ref.sha256)
    return Approved(
        item=item, decision=decision, terms=terms, attachment_id=ref.id, reviewer=reviewer, marketer=marketer
    )
