import pytest
from django.test import Client

from accounts.models import User
from audit.models import Event
from checks.models import Finding
from core.domain import FindingSource, Severity
from reviews.tests.factories import AT, make_item, make_partner, make_version


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_lead_creates_and_updates_a_partner(lead: User) -> None:
    client = _client(lead)

    created = client.post("/api/partners", {"name": "LendStack", "type": "lead_gen"}, content_type="application/json")
    assert created.status_code == 201, created.content
    partner_id = created.json()["id"]

    updated = client.patch(f"/api/partners/{partner_id}", {"status": "paused"}, content_type="application/json")

    assert updated.json()["status"] == "paused"
    assert list(Event.objects.order_by("id").values_list("type", flat=True)) == ["partner.created", "partner.updated"]


@pytest.mark.django_db
def test_partner_names_are_unique_ignoring_case(lead: User) -> None:
    make_partner("LendStack")

    response = _client(lead).post(
        "/api/partners", {"name": "lendstack", "type": "affiliate"}, content_type="application/json"
    )

    assert response.status_code == 422
    assert response.json()["fields"][0]["loc"] == ["body", "name"]


@pytest.mark.django_db
def test_reviewer_cannot_create_partner(reviewer: User) -> None:
    response = _client(reviewer).post(
        "/api/partners", {"name": "X", "type": "affiliate"}, content_type="application/json"
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_partner_detail_counts_and_repeat_issues(marketer: User, reviewer: User) -> None:
    partner = make_partner("LoanFinder")
    for _ in range(2):
        version = make_version(make_item(marketer, partner=partner, channel="affiliate_page", open_findings_count=1))
        Finding.objects.create(
            version=version,
            rule_id="ftc.material_connection",
            citation="16 CFR 255.5",
            source=FindingSource.LLM,
            severity=Severity.BLOCKING,
            message="No #ad disclosure",
            created_at=AT,
        )
    client = _client(reviewer)

    rows = client.get("/api/partners").json()
    detail = client.get(f"/api/partners/{partner.pk}").json()

    assert rows[0]["item_count"] == 2
    assert (detail["open_findings_count"], detail["approved_count"]) == (2, 0)
    assert detail["repeat_issues"] == [
        {
            "rule_id": "ftc.material_connection",
            "citation": "16 CFR 255.5",
            "count": 2,
            "items": 2,
            "last_seen_at": "2026-10-01T12:00:00Z",
        }
    ]
