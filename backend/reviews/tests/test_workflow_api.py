"""The core loop over HTTP, and the error codes the frontend switches on (thin: services carry the rules)."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from pytest_django import Settings

from accounts.models import User
from checks.models import Finding
from reviews.models import ReviewItem
from reviews.tests.conftest import RATE_COPY, ai_done
from reviews.tests.factories import make_partner
from terms.models import OfferTerms


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


SUBMISSION = {
    "title": "Spring PL landing page",
    "product": "personal_loan",
    "channel": "landing_page",
    "markets": ["national"],
    "planned_first_run": "2026-11-01",
    "content_text": RATE_COPY,
}


@pytest.mark.django_db
def test_submit_review_approve_place(marketer: User, reviewer: User, pl_terms: OfferTerms) -> None:
    m, r = _client(marketer), _client(reviewer)

    preview = m.post(
        "/api/checks/preview",
        {k: SUBMISSION[k] for k in ("content_text", "product", "channel", "markets")},
        content_type="application/json",
    )
    assert preview.status_code == 200, preview.content
    assert [t["field"] for t in preview.json()["terms_refs"]] == ["apr_min", "apr_max"]
    assert preview.json()["terms_refs"][0] == {
        "field": "apr_min",
        "span": {"start": 31, "end": 36},
        "quote": "7.49%",
        "value": "7.49",
    }

    item = m.post("/api/items", SUBMISSION, content_type="application/json").json()
    assert item["assignee"]["id"] == reviewer.pk
    assert item["open_findings_count"] > 0

    claimed = r.post(f"/api/items/{item['id']}/claim")
    assert (claimed.status_code, claimed.json()["status"]) == (200, "in_review")

    blocked = r.post(
        f"/api/items/{item['id']}/decisions",
        {"outcome": "approved", "version_n": 1, "reason": "ok"},
        content_type="application/json",
    )
    assert (blocked.status_code, blocked.json()["code"]) == (409, "open_findings_block_decision")

    for finding in r.get(f"/api/items/{item['id']}/findings").json():
        dismissed = r.post(
            f"/api/findings/{finding['id']}/dismiss", {"reason": "Checked"}, content_type="application/json"
        )
        assert (dismissed.status_code, dismissed.json()["state"]) == (200, "dismissed")

    pending = r.post(
        f"/api/items/{item['id']}/decisions",
        {"outcome": "approved", "version_n": 1, "reason": "ok"},
        content_type="application/json",
    )
    assert (pending.status_code, pending.json()["code"]) == (409, "ai_check_pending")
    ai_done(item["id"])

    decided = r.post(
        f"/api/items/{item['id']}/decisions",
        {"outcome": "approved", "version_n": 1, "reason": "Meets policy"},
        content_type="application/json",
    )
    assert decided.status_code == 201, decided.content
    body = decided.json()
    assert (body["outcome"], body["version_n"], body["terms_versions"][0]["id"]) == ("approved", 1, pl_terms.pk)
    assert body["engine_version"]

    placed = m.post(
        f"/api/items/{item['id']}/placements",
        {"location": "clearpath.com/pl", "first_run": "2026-10-24"},
        content_type="application/json",
    )
    assert (placed.status_code, placed.json()["is_live"], placed.json()["approved_version_n"]) == (201, True, 1)
    ended = m.patch(
        f"/api/placements/{placed.json()['id']}", {"last_run": "2026-12-31"}, content_type="application/json"
    )
    assert (ended.status_code, ended.json()["last_run"], ended.json()["monitored"]) == (200, "2026-12-31", False)
    history = [e["type"] for e in r.get(f"/api/items/{item['id']}/history").json()["entries"]]
    assert history[-2:] == ["placement.recorded", "placement.updated"]


@pytest.mark.django_db
def test_edits_that_raise_findings_return_them_with_the_code(
    marketer: User, reviewer: User, pl_terms: OfferTerms
) -> None:
    m, r = _client(marketer), _client(reviewer)
    item = m.post("/api/items", SUBMISSION, content_type="application/json").json()
    for finding in r.get(f"/api/items/{item['id']}/findings").json():
        r.post(f"/api/findings/{finding['id']}/dismiss", {"reason": "Checked"}, content_type="application/json")
    ai_done(item["id"])

    response = r.post(
        f"/api/items/{item['id']}/decisions",
        {
            "outcome": "approved_with_edits",
            "version_n": 1,
            "reason": "Tightened",
            "edited_content_text": "Guaranteed approval. " + RATE_COPY,
        },
        content_type="application/json",
    )

    assert response.status_code == 409
    body = response.json()
    assert (body["code"], body["details"]["version_n"]) == ("findings_need_triage", 2)
    assert "claims.guaranteed" in {f["rule_id"] for f in body["details"]["findings"]}
    assert ReviewItem.objects.get(pk=item["id"]).current_version.n == 2  # pyrefly: ignore[missing-attribute]


@pytest.mark.django_db
def test_text_only_with_approve_with_edits(reviewer: User) -> None:
    response = _client(reviewer).post(
        "/api/items/1/decisions",
        {"outcome": "approved", "version_n": 1, "reason": "x", "edited_content_text": "y"},
        content_type="application/json",
    )

    assert (response.status_code, response.json()["code"]) == (422, "validation_error")


@pytest.mark.django_db
def test_marketers_cannot_read_partner_attachments(
    marketer: User, reviewer: User, lead: User, settings: Settings, tmp_path: Path
) -> None:
    settings.MEDIA_ROOT = tmp_path
    partner = make_partner()
    uploaded = _client(lead).post(
        f"/api/partners/{partner.pk}/attachments",
        {"kind": "agreement", "file": SimpleUploadedFile("agreement.pdf", b"signed")},
    )
    assert uploaded.status_code == 201, uploaded.content
    download = uploaded.json()["download_url"]
    m, r = _client(marketer), _client(reviewer)

    assert m.get(f"/api/partners/{partner.pk}").json()["attachments"] == []
    assert m.get(f"/api/partners/{partner.pk}/attachments").status_code == 403
    assert m.get(download).status_code == 403
    assert len(r.get(f"/api/partners/{partner.pk}").json()["attachments"]) == 1
    assert r.get(download).status_code == 200


@pytest.mark.django_db
def test_item_evidence_is_readable_by_any_signed_in_user(
    marketer: User, user_factory: object, settings: Settings, tmp_path: Path
) -> None:
    settings.MEDIA_ROOT = tmp_path
    item = _client(marketer).post("/api/items", SUBMISSION, content_type="application/json").json()
    uploaded = _client(marketer).post(
        f"/api/items/{item['id']}/attachments",
        {"kind": "substantiation", "file": SimpleUploadedFile("memo.pdf", b"memo")},
    )
    other = user_factory()  # pyrefly: ignore[not-callable]

    assert _client(other).get(uploaded.json()["download_url"]).status_code == 200


@pytest.mark.django_db
def test_bulk_assign_reports_skips(marketer: User, reviewer: User, lead: User) -> None:
    m = _client(marketer)
    first = m.post("/api/items", SUBMISSION, content_type="application/json").json()

    response = _client(lead).post(
        "/api/items/bulk/assign",
        {"item_ids": [first["id"], 999_999], "assignee_id": None, "reason": "rebalancing"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "succeeded": [first["id"]],
        "skipped": [{"item_id": 999_999, "code": "not_found", "message": "Item 999999 doesn't exist."}],
    }
    assert Finding.objects.exists()
