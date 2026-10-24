"""Code checks wired into persistence (`checks.services`): findings, terms refs, check runs, carry-forward."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import transaction

from accounts.models import User
from audit.models import Event
from checks.engine import ENGINE_VERSION, RULESET_VERSION, FindingDraft, Span
from checks.models import CheckRun, Finding, TermsRef
from checks.selectors import list_findings
from checks.services import (
    PreviewInput,
    persist_findings,
    preview_checks,
    recount_open_findings,
    rule_context,
    run_code_checks,
)
from core.clock import FixedClock
from core.domain import (
    AttachmentKind,
    Channel,
    CheckStatus,
    EventType,
    FindingSource,
    FindingState,
    FixKind,
    Market,
    Product,
    Severity,
    TermsField,
)
from reviews.models import ReviewItem, Version
from reviews.tests.conftest import CLEAN_COPY, RATE_COPY, Submit
from reviews.tests.factories import make_item, make_partner, make_version
from terms.models import OfferTerms

RULESET_KEY = f"{RULESET_VERSION.isoformat()}/{ENGINE_VERSION}"


def _findings(version_id: int) -> list[Finding]:
    return list(Finding.objects.filter(version_id=version_id).order_by("rule_id"))


@pytest.mark.django_db
def test_submit_persists_code_and_human_findings_with_the_open_count(
    submit: Submit, pl_terms: OfferTerms, clock: FixedClock
) -> None:
    result = submit(content_text="Guaranteed approval for personal loans.")

    findings = _findings(result.version_id)
    by_rule = {f.rule_id: f for f in findings}
    guaranteed = by_rule["claims.guaranteed"]
    assert (guaranteed.source, guaranteed.severity, guaranteed.state) == ("code", "blocking", "open")
    assert (guaranteed.span_start, guaranteed.span_end, guaranteed.quote) == (0, 10, "Guaranteed")
    assert guaranteed.citation.startswith("12 U.S.C. 5536")
    assert guaranteed.created_at == clock.now()
    human = by_rule["human.reg_b_discouragement"]
    assert (human.source, human.span_start, human.quote) == ("human", None, None)
    assert result.open_findings_count == len(findings)
    assert ReviewItem.objects.get(pk=result.item_id).open_findings_count == len(findings)


@pytest.mark.django_db
def test_terms_refs_point_at_the_offer_terms_in_effect(submit: Submit, pl_terms: OfferTerms) -> None:
    result = submit(content_text=RATE_COPY)

    refs = list(TermsRef.objects.filter(version_id=result.version_id).order_by("span_start"))
    assert [(r.field, r.quoted_value, r.quote, r.offer_terms_id) for r in refs] == [  # pyrefly: ignore[missing-attribute]
        (TermsField.APR_MIN, Decimal("7.49"), "7.49%", pl_terms.pk),
        (TermsField.APR_MAX, Decimal("35.99"), "35.99%", pl_terms.pk),
    ]


@pytest.mark.django_db
def test_no_terms_in_effect_means_no_refs(submit: Submit) -> None:
    result = submit(content_text=RATE_COPY)

    assert not TermsRef.objects.filter(version_id=result.version_id).exists()


@pytest.mark.django_db
def test_check_run_and_event_record_the_engine_version(submit: Submit, pl_terms: OfferTerms, clock: FixedClock) -> None:
    result = submit(content_text="Guaranteed approval for personal loans.")

    run = CheckRun.objects.get(version_id=result.version_id)
    version = Version.objects.get(pk=result.version_id)
    assert (run.source, run.status, run.ruleset_key) == ("code", CheckStatus.SUCCEEDED, RULESET_KEY)
    assert (run.content_sha256, run.started_at, run.finished_at) == (version.content_sha256, clock.now(), clock.now())
    assert run.findings_count == Finding.objects.filter(version=version, source="code").count()
    event = Event.objects.get(type=EventType.CHECKS_COMPLETED, item_id=result.item_id)
    assert event.payload == {
        "version_id": version.pk,
        "source": "code",
        "findings_count": Finding.objects.filter(version=version).count(),
        "blocking_count": 1,
        "ruleset_key": RULESET_KEY,
    }


@pytest.mark.django_db
def test_rule_context_reads_item_attachments_partner_and_terms(
    marketer: User, pl_terms: OfferTerms, clock: FixedClock
) -> None:
    partner = make_partner()
    item = make_item(marketer, channel=Channel.AFFILIATE_PAGE, partner=partner, markets=[Market.NATIONAL, Market.CA])
    version = make_version(item, "Rates from 7.49% APR.")
    from reviews.models import Attachment

    Attachment.objects.create(
        version=version,
        kind=AttachmentKind.SUBSTANTIATION,
        file="x.pdf",
        original_name="x.pdf",
        content_type="application/pdf",
        size_bytes=1,
        sha256="a" * 64,
        uploaded_by=marketer,
        uploaded_at=clock.now(),
    )

    ctx = rule_context(version=version, clock=clock)

    assert (ctx.product, ctx.channel, ctx.markets) == (
        Product.PERSONAL_LOAN,
        Channel.AFFILIATE_PAGE,
        frozenset({Market.NATIONAL, Market.CA}),
    )
    assert ctx.partner_type == partner.type
    assert ctx.attachment_kinds == frozenset({AttachmentKind.SUBSTANTIATION})
    assert ctx.terms == pl_terms.typed_values
    assert ctx.today == clock.today()


def _dismiss(finding: Finding, by: User, at: object, reason: str = "Footer carries it") -> None:
    Finding.objects.filter(pk=finding.pk).update(
        state=FindingState.DISMISSED, reason=reason, resolved_by=by, resolved_at=at
    )


@pytest.mark.django_db
def test_identical_dismissed_finding_is_carried_forward(
    marketer: User, reviewer: User, clock: FixedClock, pl_terms: OfferTerms
) -> None:
    item = make_item(marketer)
    v1 = make_version(item, "Guaranteed approval. Apply now.")
    with transaction.atomic():
        run_code_checks(version=v1, clock=clock)
    guaranteed = Finding.objects.get(version=v1, rule_id="claims.guaranteed")
    _dismiss(guaranteed, reviewer, clock.now())
    clock.advance(timedelta(days=1))
    v2 = make_version(item, "Guaranteed approval. Apply today.", n=2)

    with transaction.atomic():
        checks = run_code_checks(version=v2, clock=clock)

    carried = Finding.objects.get(version=v2, rule_id="claims.guaranteed")
    assert (carried.state, carried.carried_from_id, carried.reason) == ("dismissed", guaranteed.pk, "Footer carries it")  # pyrefly: ignore[missing-attribute]
    assert (carried.resolved_by, carried.resolved_at) == (reviewer, clock.now())
    assert checks.open_findings_count == Finding.objects.filter(version=v2, state="open").count()
    event = Event.objects.get(type=EventType.FINDING_DISMISSED, entity_id=carried.pk)
    assert event.actor is None
    assert event.payload["carried"] is True


@pytest.mark.django_db
def test_a_later_accept_beats_an_older_dismissal(marketer: User, reviewer: User, clock: FixedClock) -> None:
    # Review finding 1: v1 dismissed, v2 (same text) accepted as a real problem; v3 must not resurrect v1's dismissal.
    item = make_item(marketer)
    versions = []
    for n in (1, 2, 3):
        version = make_version(item, "Guaranteed approval.", n=n)
        with transaction.atomic():
            run_code_checks(version=version, clock=clock)
        finding = Finding.objects.get(version=version, rule_id="claims.guaranteed")
        if n == 1:
            _dismiss(finding, reviewer, clock.now())
        elif n == 2:
            assert finding.state == "dismissed"  # carried from v1
            Finding.objects.filter(pk=finding.pk).update(state=FindingState.ACCEPTED, carried_from=None)
        versions.append(finding)

    assert (versions[2].state, versions[2].carried_from_id) == ("open", None)  # pyrefly: ignore[missing-attribute]


@pytest.mark.django_db
def test_human_checklist_dismissals_carry_only_into_text_only_versions(
    marketer: User, reviewer: User, clock: FixedClock
) -> None:
    from core.domain import VersionOrigin

    item = make_item(marketer)
    v1 = make_version(item, "Personal loans.")
    with transaction.atomic():
        run_code_checks(version=v1, clock=clock)
    _dismiss(Finding.objects.get(version=v1, source="human"), reviewer, clock.now(), reason="Imagery fine")
    resubmitted = make_version(item, "Personal loans.", n=2)
    edited = make_version(item, "Personal loans.", n=3, origin=VersionOrigin.REVIEWER_EDIT, author=reviewer)

    with transaction.atomic():
        run_code_checks(version=resubmitted, clock=clock)
    _dismiss(Finding.objects.get(version=resubmitted, source="human"), reviewer, clock.now(), reason="New mockup ok")
    with transaction.atomic():
        run_code_checks(version=edited, clock=clock)

    assert Finding.objects.get(version=edited, source="human").reason == "New mockup ok"
    # A marketer's resubmission may carry a new creative: the checklist starts open again.
    item2 = make_item(marketer)
    a = make_version(item2, "Personal loans.")
    with transaction.atomic():
        run_code_checks(version=a, clock=clock)
    _dismiss(Finding.objects.get(version=a, source="human"), reviewer, clock.now())
    b = make_version(item2, "Personal loans.", n=2)
    with transaction.atomic():
        run_code_checks(version=b, clock=clock)
    assert Finding.objects.get(version=b, source="human").state == "open"


@pytest.mark.django_db
def test_a_different_quote_is_not_carried(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer)
    v1 = make_version(item, "Guaranteed approval.")
    with transaction.atomic():
        run_code_checks(version=v1, clock=clock)
    _dismiss(Finding.objects.get(version=v1, rule_id="claims.guaranteed"), reviewer, clock.now())
    v2 = make_version(item, "GUARANTEED approval.", n=2)

    with transaction.atomic():
        run_code_checks(version=v2, clock=clock)

    assert Finding.objects.get(version=v2, rule_id="claims.guaranteed").state == "open"


@pytest.mark.django_db
def test_persist_findings_dedupes_on_the_unique_key(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer)
    version = make_version(item, "Guaranteed.")
    draft = FindingDraft(
        rule_id="claims.guaranteed",
        source=FindingSource.CODE,
        severity=Severity.BLOCKING,
        message="one",
        citation="c",
        suggested_fix=None,
        span=Span(0, 10),
        quote="Guaranteed",
    )
    twin = replace(draft, message="two")

    with transaction.atomic():
        created = persist_findings(version=version, drafts=[draft, twin], clock=clock)

    assert created == 1
    assert Finding.objects.get(version=version).message == "one"


@pytest.mark.django_db
def test_a_findings_fix_kind_and_text_are_kept_and_read_back(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer)
    version = make_version(item, "Talk to a counselor.")
    draft = FindingDraft(
        rule_id="mortgage.counselor",
        source=FindingSource.CODE,
        severity=Severity.WARNING,
        message="m",
        citation="c",
        suggested_fix='"loan officer"',
        span=Span(10, 19),
        quote="counselor",
        fix_kind=FixKind.REPLACE,
        replacement_text="loan officer",
    )
    unknown = replace(draft, rule_id="claims.guaranteed", fix_kind=None, replacement_text=None)
    with transaction.atomic():
        persist_findings(version=version, drafts=[draft, unknown], clock=clock)

    rows = {f.rule_id: f for f in list_findings(item_id=item.pk)}
    assert (rows["mortgage.counselor"].fix_kind, rows["mortgage.counselor"].replacement_text) == (
        FixKind.REPLACE,
        "loan officer",
    )
    assert (rows["claims.guaranteed"].fix_kind, rows["claims.guaranteed"].replacement_text) == (None, None)


@pytest.mark.django_db
def test_recount_writes_the_current_versions_open_count(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer)
    v1 = make_version(item, "Guaranteed approval.")
    with transaction.atomic():
        run_code_checks(version=v1, clock=clock)
    _dismiss(Finding.objects.get(version=v1, rule_id="claims.guaranteed"), reviewer, clock.now())

    with transaction.atomic():
        count = recount_open_findings(item_id=item.pk)

    assert count == Finding.objects.filter(version=v1, state="open").count()
    assert ReviewItem.objects.get(pk=item.pk).open_findings_count == count


@pytest.mark.django_db
def test_preview_returns_findings_and_refs_and_stores_nothing(pl_terms: OfferTerms, clock: FixedClock) -> None:
    result = preview_checks(
        data=PreviewInput(
            content_text=RATE_COPY + " Guaranteed approval.",
            product=Product.PERSONAL_LOAN,
            channel=Channel.LANDING_PAGE,
            markets=(Market.NATIONAL,),
        ),
        clock=clock,
    )

    assert {f.rule_id for f in result.findings} >= {"claims.guaranteed", "pricing.creditworthiness_qualifier"}
    assert all(f.source is FindingSource.CODE for f in result.findings)
    assert [r.field for r in result.terms_refs] == ["apr_min", "apr_max"]
    assert result.ruleset_key == RULESET_KEY
    assert not Finding.objects.exists()
    assert not CheckRun.objects.exists()


@pytest.mark.django_db
def test_preview_uses_the_partner_type(clock: FixedClock) -> None:
    partner = make_partner()
    base = PreviewInput(
        content_text=CLEAN_COPY, product=Product.PERSONAL_LOAN, channel=Channel.LANDING_PAGE, markets=(Market.NATIONAL,)
    )

    without = preview_checks(data=base, clock=clock)
    with_partner = preview_checks(data=replace(base, partner_id=partner.pk), clock=clock)

    assert "endorsement.material_connection" not in {f.rule_id for f in without.findings}
    assert "endorsement.material_connection" in {f.rule_id for f in with_partner.findings}


@pytest.mark.django_db
def test_preview_uses_the_attachment_kinds(clock: FixedClock) -> None:
    base = PreviewInput(
        content_text="Reply YES for rate alerts. Reply STOP to opt out.",
        product=Product.PERSONAL_LOAN,
        channel=Channel.SMS,
        markets=(Market.NATIONAL,),
    )

    without = preview_checks(data=base, clock=clock)
    with_consent = preview_checks(data=replace(base, attachment_kinds=(AttachmentKind.CONSENT_RECORD,)), clock=clock)

    assert "sms.consent_record" in {f.rule_id for f in without.findings}
    assert "sms.consent_record" not in {f.rule_id for f in with_consent.findings}


@pytest.mark.django_db
def test_preview_with_an_unknown_partner_is_not_found(clock: FixedClock) -> None:
    from core.errors import NotFound

    with pytest.raises(NotFound):
        preview_checks(
            data=PreviewInput(
                content_text="x",
                product=Product.PERSONAL_LOAN,
                channel=Channel.LANDING_PAGE,
                markets=(Market.NATIONAL,),
                partner_id=999_999,
            ),
            clock=clock,
        )
