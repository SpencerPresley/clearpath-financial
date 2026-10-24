from datetime import UTC, datetime, timedelta

import pytest
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test import Client

from accounts.models import User
from terms.models import OfferTerms
from terms.tests.test_models import CC, PL


@pytest.mark.django_db
def test_terms_list_current_and_detail(lead: User, reviewer: User) -> None:
    now = datetime.now(tz=UTC)
    old = OfferTerms.objects.create(
        product="personal_loan",
        version=1,
        effective_range=DateTimeTZRange(now - timedelta(days=60), now - timedelta(days=1), "[)"),
        values=PL.model_dump(mode="json"),
        created_by=lead,
        created_at=now,
    )
    current = OfferTerms.objects.create(
        product="personal_loan",
        version=2,
        effective_range=DateTimeTZRange(now - timedelta(days=1), None, "[)"),
        values=PL.model_dump(mode="json"),
        created_by=lead,
        created_at=now,
    )
    OfferTerms.objects.create(
        product="credit_card",
        version=1,
        effective_range=DateTimeTZRange(now - timedelta(days=1), None, "[)"),
        values=CC.model_dump(mode="json"),
        created_by=lead,
        created_at=now,
    )
    client = Client()
    client.force_login(reviewer)

    listed = client.get("/api/terms?product=personal_loan").json()
    current_terms = client.get("/api/terms/current").json()
    detail = client.get(f"/api/terms/{old.pk}").json()

    assert [t["version"] for t in listed] == [2, 1]
    assert {(t["product"], t["version"]) for t in current_terms} == {("personal_loan", 2), ("credit_card", 1)}
    assert detail["is_current"] is False
    assert detail["effective_to"] is not None
    assert detail["values"]["apr_min"] == "7.49"
    assert next(t for t in listed if t["id"] == current.pk)["is_current"] is True


@pytest.mark.django_db
def test_publish_api_lead_only(pl_terms: OfferTerms, lead: User, reviewer: User) -> None:
    values = {**PL.model_dump(mode="json"), "apr_min": "12.99"}
    body = {"product": "personal_loan", "values": values, "based_on_terms_id": pl_terms.pk, "note": "Q4"}
    client = Client()
    client.force_login(reviewer)

    refused = client.post("/api/terms", body, content_type="application/json")
    client.force_login(lead)
    created = client.post("/api/terms", body, content_type="application/json")
    stale = client.post("/api/terms", body, content_type="application/json")
    unchanged = client.post(
        "/api/terms", {**body, "based_on_terms_id": created.json()["id"]}, content_type="application/json"
    )

    assert refused.status_code == 403
    assert created.status_code == 201, created.content
    assert (created.json()["version"], created.json()["is_current"], created.json()["note"]) == (2, True, "Q4")
    assert created.json()["values"]["apr_min"] == "12.99"
    assert (stale.status_code, stale.json()["code"]) == (409, "conflict")
    assert unchanged.status_code == 422
    assert unchanged.json()["fields"][0]["loc"] == ["body", "values"]
