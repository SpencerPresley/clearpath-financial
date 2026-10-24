"""A partner's findings history: `GET /partners/{id}/findings` (listPartnerFindings)."""

from datetime import timedelta
from itertools import count

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from checks.models import Finding
from core.domain import FindingSource, FindingState, Severity
from partners.models import Partner
from partners.selectors import list_partner_findings
from reviews.models import Version
from reviews.tests.factories import AT, make_item, make_partner, make_version

_serial = count(1)


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _finding(version: Version, *, minutes: int, rule_id: str = "reg_z.trigger_terms", **overrides: object) -> Finding:
    fields: dict[str, object] = {
        "version": version,
        "rule_id": rule_id,
        "citation": "Reg Z 1026.24(d)",
        "source": FindingSource.CODE,
        "severity": Severity.BLOCKING,
        "message": "Trigger term without the full disclosures.",
        "created_at": AT + timedelta(minutes=minutes),
    }
    fields.update(overrides)
    return Finding.objects.create(**fields)


def _partner_version(owner: User, partner: Partner, *, n: int = 1) -> Version:
    item = make_item(owner, partner=partner, title=f"Affiliate page {next(_serial)}", channel="affiliate_page")
    return make_version(item, n=n)


@pytest.mark.django_db
def test_findings_newest_first_with_item_and_version(marketer: User, reviewer: User) -> None:
    partner = make_partner("LoanFinder")
    version = _partner_version(marketer, partner)
    item = version.item
    _finding(
        version,
        minutes=1,
        rule_id="ftc.material_connection",
        citation="16 CFR 255.5",
        source=FindingSource.LLM,
        severity=Severity.WARNING,  # AI findings are never blocking (ledger ruling, enforced by a constraint)
    )
    _finding(
        version,
        minutes=2,
        state=FindingState.DISMISSED,
        reason="Disclosure is in the footer.",
        resolved_by=reviewer,
        resolved_at=AT,
    )
    other = make_partner("Elsewhere")
    _finding(_partner_version(marketer, other), minutes=3)

    response = _client(reviewer).get(f"/api/partners/{partner.pk}/findings")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["next_cursor"] is None
    assert [r["rule_id"] for r in body["rows"]] == ["reg_z.trigger_terms", "ftc.material_connection"]
    newest = body["rows"][0]
    assert newest == {
        "id": newest["id"],
        "item_id": item.pk,
        "item_key": f"CP-{item.pk}",
        "item_title": item.title,
        "item_is_legacy": False,
        "version_n": 1,
        "rule_id": "reg_z.trigger_terms",
        "citation": "Reg Z 1026.24(d)",
        "source": "code",
        "severity": "blocking",
        "state": "dismissed",
        "message": "Trigger term without the full disclosures.",
        "created_at": "2026-10-01T12:02:00Z",
    }
    assert body["rows"][1]["source"] == "llm"


@pytest.mark.django_db
def test_findings_paginate_by_cursor_without_gaps_or_repeats(marketer: User, lead: User) -> None:
    partner = make_partner()
    version = _partner_version(marketer, partner)
    # Two findings share a timestamp: the id breaks the tie, so the page boundary can fall between them.
    ids = [_finding(version, minutes=m, rule_id=f"R{i}").pk for i, m in enumerate([1, 2, 2, 3, 4])]
    client = _client(lead)

    first = client.get(f"/api/partners/{partner.pk}/findings?limit=2").json()
    second = client.get(f"/api/partners/{partner.pk}/findings?limit=2&cursor={first['next_cursor']}").json()
    third = client.get(f"/api/partners/{partner.pk}/findings?limit=2&cursor={second['next_cursor']}").json()

    seen = [r["id"] for page in (first, second, third) for r in page["rows"]]
    assert seen == [ids[4], ids[3], ids[2], ids[1], ids[0]]
    assert third["next_cursor"] is None


@pytest.mark.django_db
def test_a_bad_cursor_is_a_422_that_says_reload(lead: User) -> None:
    partner = make_partner()

    response = _client(lead).get(f"/api/partners/{partner.pk}/findings?cursor=not-a-cursor")

    assert response.status_code == 422
    assert response.json()["message"] == "This page link is out of date. Reload the list."


@pytest.mark.django_db
def test_findings_need_a_reviewer_and_a_real_partner(marketer: User, reviewer: User) -> None:
    partner = make_partner()

    assert _client(marketer).get(f"/api/partners/{partner.pk}/findings").status_code == 403
    assert _client(reviewer).get("/api/partners/999999/findings").status_code == 404


@pytest.mark.django_db
def test_findings_history_costs_the_same_queries_whatever_the_rows(marketer: User, lead: User) -> None:
    partner = make_partner()
    client = _client(lead)

    def grow(k: int) -> None:
        for _ in range(k):
            version = _partner_version(marketer, partner)
            _finding(version, minutes=next(_serial))
            _finding(make_version(version.item, n=2), minutes=next(_serial), source=FindingSource.HUMAN)

    def measure() -> int:
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f"/api/partners/{partner.pk}/findings")
        assert response.status_code == 200
        return len(ctx.captured_queries)

    grow(1)
    small = measure()
    grow(4)
    large = measure()

    assert large == small
    assert len(list_partner_findings(partner_id=partner.pk, viewer=lead).rows) == 10
