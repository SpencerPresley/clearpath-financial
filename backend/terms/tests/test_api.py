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
