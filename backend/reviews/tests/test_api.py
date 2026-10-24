from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from pytest_django import Settings

from accounts.models import User
from checks.models import Finding
from core.domain import FindingSource, Severity
from reviews.models import ReviewItem
from reviews.tests.factories import AT, make_item, make_version

SUBMISSION = {
    "title": "Spring PL email",
    "product": "personal_loan",
    "channel": "email",
    "markets": ["national", "CA"],
    "planned_first_run": "2026-11-01",
    "content_text": "Rates from 7.49% APR. Checking your rate won't affect your credit score.",
    "tags": ["spring"],
}


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize("tag", ["x" * 51, ""])
def test_tags_longer_than_the_column_or_empty_are_rejected_not_truncated(marketer: User, tag: str) -> None:
    client = _client(marketer)

    created = client.post("/api/items", {**SUBMISSION, "tags": [tag]}, content_type="application/json")
    item = make_item(marketer)
    updated = client.patch(f"/api/items/{item.pk}", {"tags": [tag]}, content_type="application/json")

    assert (created.status_code, updated.status_code) == (422, 422)
    assert created.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_submit_item_round_trip(marketer: User) -> None:
    client = _client(marketer)

    created = client.post("/api/items", SUBMISSION, content_type="application/json")

    assert created.status_code == 201, created.content
    body = created.json()
    assert (body["status"], body["round"], body["risk_tier"], body["llm_check_status"]) == (
        "submitted",
        1,
        "low",
        "pending",
    )
    assert body["key"] == f"CP-{body['id']}"
    assert body["current_version"]["n"] == 1
    assert body["current_version"]["content_text"] == SUBMISSION["content_text"]
    assert body["owner"] == {"id": marketer.pk, "name": "Morgan Marketer"}
    assert body["latest_decision"] is None

    fetched = client.get(f"/api/items/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body

    history = client.get(f"/api/items/{body['id']}/history").json()["entries"]
    assert [e["type"] for e in history] == ["item.submitted"]
    assert history[0]["payload"]["version_n"] == 1
    assert history[0]["to_status"] == "submitted"


@pytest.mark.django_db
def test_submit_affiliate_without_partner_points_at_the_field(marketer: User) -> None:
    response = _client(marketer).post(
        "/api/items", {**SUBMISSION, "channel": "affiliate_page"}, content_type="application/json"
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"
    assert response.json()["fields"][0]["loc"] == ["body", "partner_id"]


@pytest.mark.django_db
def test_reviewer_cannot_submit(reviewer: User) -> None:
    response = _client(reviewer).post("/api/items", SUBMISSION, content_type="application/json")

    assert response.status_code == 403
    assert response.json()["code"] == "not_permitted"


@pytest.mark.django_db
def test_list_items_accepts_repeated_filters_and_pages(marketer: User, reviewer: User) -> None:
    submitted = [make_item(marketer) for _ in range(3)]
    make_item(marketer, status="approved")
    client = _client(reviewer)

    first = client.get("/api/items?status=submitted&status=in_review&limit=2").json()
    second = client.get(f"/api/items?status=submitted&status=in_review&limit=2&cursor={first['next_cursor']}").json()

    ids = [r["id"] for r in first["rows"] + second["rows"]]
    assert sorted(ids) == sorted(i.pk for i in submitted)
    assert second["next_cursor"] is None


@pytest.mark.django_db
def test_bad_query_values_are_validation_errors(reviewer: User) -> None:
    client = _client(reviewer)

    assert client.get("/api/items?status=bogus").status_code == 422
    assert client.get("/api/items?limit=0").status_code == 422
    assert client.get("/api/items?cursor=garbage").json()["code"] == "invalid_input"


@pytest.mark.django_db
def test_unknown_item_is_404_envelope(reviewer: User) -> None:
    response = _client(reviewer).get("/api/items/999999")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


@pytest.mark.django_db
def test_queue_stats(marketer: User, reviewer: User) -> None:
    make_item(marketer, assignee=reviewer)

    stats = _client(reviewer).get("/api/items/stats").json()

    assert (stats["open"], stats["mine"]) == (1, 1)


@pytest.mark.django_db
def test_marketer_cannot_update_risk_tier(marketer: User) -> None:
    item = make_item(marketer)

    response = _client(marketer).patch(f"/api/items/{item.pk}", {"risk_tier": "high"}, content_type="application/json")

    assert response.status_code == 403
    assert response.json()["details"] == {"required_any_of": ["reviewer"]}


@pytest.mark.django_db
def test_reviewer_updates_tags_inline(marketer: User, reviewer: User) -> None:
    item = make_item(marketer)

    response = _client(reviewer).patch(
        f"/api/items/{item.pk}", {"tags": ["q4", "promo"]}, content_type="application/json"
    )

    assert response.status_code == 200
    assert response.json()["tags"] == ["q4", "promo"]


@pytest.mark.django_db
def test_versions_diff_and_version_detail(marketer: User, reviewer: User) -> None:
    item = make_item(marketer)
    make_version(item, "Rates from 7.49% APR.", n=1)
    make_version(item, "Rates from 6.99% APR.", n=2)
    client = _client(reviewer)

    versions = client.get(f"/api/items/{item.pk}/versions").json()
    diff = client.get(f"/api/items/{item.pk}/diff?from_n=1&to_n=2").json()
    v2 = client.get(f"/api/items/{item.pk}/versions/2").json()

    assert [v["n"] for v in versions] == [1, 2]
    assert {"op": "delete", "text": "7.49"} in diff["segments"]
    assert v2["content_text"] == "Rates from 6.99% APR."
    assert client.get(f"/api/items/{item.pk}/versions/9").status_code == 404


@pytest.mark.django_db
def test_comments_round_trip_with_mentions(marketer: User, reviewer: User) -> None:
    item = make_item(marketer)
    make_version(item, "Rates from 7.49% APR.")
    client = _client(reviewer)

    created = client.post(
        f"/api/items/{item.pk}/comments",
        {"body": "Range?", "span_start": 11, "span_end": 16, "mention_user_ids": [marketer.pk]},
        content_type="application/json",
    )

    assert created.status_code == 201, created.content
    assert created.json()["span"] == {"start": 11, "end": 16}
    assert created.json()["mentions"] == [{"id": marketer.pk, "name": "Morgan Marketer"}]
    assert len(client.get(f"/api/items/{item.pk}/comments").json()) == 1


@pytest.mark.django_db
def test_attachment_upload_list_and_download(marketer: User, settings: Settings, tmp_path: Path) -> None:
    settings.MEDIA_ROOT = tmp_path
    item = make_item(marketer)
    client = _client(marketer)

    uploaded = client.post(
        f"/api/items/{item.pk}/attachments",
        {"kind": "substantiation", "file": SimpleUploadedFile("memo.pdf", b"memo", content_type="application/pdf")},
    )

    assert uploaded.status_code == 201, uploaded.content
    attachment = uploaded.json()
    assert attachment["kind"] == "substantiation"
    assert client.get(f"/api/items/{item.pk}/attachments").json() == [attachment]
    download = client.get(attachment["download_url"])
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == b"memo"  # pyrefly: ignore[missing-attribute]


@pytest.mark.django_db
def test_findings_listed_for_the_current_version(marketer: User, reviewer: User) -> None:
    item = make_item(marketer)
    version = make_version(item, "Rates as low as 7.49% APR.")
    Finding.objects.create(
        version=version,
        rule_id="reg_z.as_low_as",
        citation="Reg Z 1026.24(a)",
        source=FindingSource.CODE,
        severity=Severity.BLOCKING,
        span_start=6,
        span_end=15,
        quote="as low as",
        message="Needs the full range",
        created_at=AT,
    )

    findings = _client(reviewer).get(f"/api/items/{item.pk}/findings").json()

    assert [(f["rule_id"], f["span"], f["state"]) for f in findings] == [
        ("reg_z.as_low_as", {"start": 6, "end": 15}, "open")
    ]


@pytest.mark.django_db
def test_saved_views_round_trip(reviewer: User) -> None:
    client = _client(reviewer)

    created = client.post(
        "/api/views",
        {
            "name": "Waiting > 3 days",
            "filters": {"waiting_more_than_days": 3, "status": ["submitted"]},
            "sort": "oldest",
        },
        content_type="application/json",
    )
    assert created.status_code == 201, created.content
    view = created.json()
    assert view["filters"]["waiting_more_than_days"] == 3

    assert (
        client.post(
            "/api/views", {"name": "Waiting > 3 days", "filters": {}}, content_type="application/json"
        ).status_code
        == 422
    )
    assert client.delete(f"/api/views/{view['id']}").status_code == 204
    assert client.get("/api/views").json() == []


@pytest.mark.django_db
def test_library_lists_approved_and_searches(marketer: User, reviewer: User) -> None:
    approved = make_item(marketer, status="approved")
    make_version(approved, "Checking your rate won't affect your credit score.")
    make_version(make_item(marketer), "Checking your rate won't affect your credit score.")
    client = _client(reviewer)

    library = client.get("/api/library").json()
    phrase = client.get("/api/library/search?mode=phrase&query=affect your credit&status=approved").json()
    text = client.get("/api/library/search?query=credit%20score").json()

    assert [r["id"] for r in library["rows"]] == [approved.pk]
    assert [h["item_id"] for h in phrase["hits"]] == [approved.pk]
    assert len(text["hits"]) == 2
    assert ReviewItem.objects.count() == 2
