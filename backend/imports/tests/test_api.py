"""The import flow through HTTP, as the Import page drives it."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from core.domain import Role
from imports.workbook import SAMPLE_TRACKER_PATH
from reviews.models import ReviewItem

pytestmark = pytest.mark.django_db

type OnCommit = Callable[..., AbstractContextManager[list[Callable[[], Any]]]]


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def test_sample_flow_load_map_preview_commit(admin_user: User, django_capture_on_commit_callbacks: OnCommit) -> None:
    client = _client(admin_user)

    loaded = client.post("/api/imports/sample")
    assert loaded.status_code == 201, loaded.content
    job = loaded.json()
    assert (job["status"], job["sheet_name"], job["row_count"]) == ("uploaded", "Review Tracker", 180)
    assert {c["name"]: c["field"] for c in job["columns"]}["Asset Name / File Link"] == "title"
    statuses = {v["source_value"]: v for v in job["status_values"]}
    assert statuses["Pending"] == {
        "source_value": "Pending",
        "rows": 3,
        "status": "submitted",
        "outcome": None,
        "source": "default",
    }

    mapped = client.put(
        f"/api/imports/{job['id']}/mapping",
        {
            "columns": [{"source": "Live URL / Placement & Screenshot Link", "target": "ignore"}],
            "status_values": [{"source_value": "Pending", "status": "in_review"}],
        },
        content_type="application/json",
    )
    assert mapped.status_code == 200, mapped.content
    preview = mapped.json()
    assert preview["counts"] == {
        "rows_total": 180,
        "ready": 178,
        "duplicates": 1,
        "already_imported": 0,
        "not_data": 1,
        "blocked": 0,
    }
    assert {p["kind"] for p in preview["problems"]} >= {"duplicate_row", "reused_ref", "not_data_row", "fuzzy_partner"}
    assert {r["row_number"]: r["status"] for r in preview["rows"]}[172] == "in_review"  # MCR-26-151, "Pending"

    with django_capture_on_commit_callbacks(execute=True):
        committed = client.post(f"/api/imports/{job['id']}/commit", {}, content_type="application/json")
    assert committed.status_code == 202, committed.content

    final = client.get(f"/api/imports/{job['id']}").json()
    assert final["status"] == "committed"
    assert final["summary"] == {"created": 178, "skipped": 2, "partners_created": 8}
    assert ReviewItem.objects.filter(is_legacy=True).count() == 178
    after = client.get(f"/api/imports/{job['id']}/preview").json()
    assert after["status"] == "committed"
    assert after["counts"]["ready"] == 178

    listed = client.get("/api/imports").json()
    assert [j["id"] for j in listed] == [job["id"]]
    assert "columns" not in listed[0]


def test_imported_open_items_stay_out_of_the_review_queue(
    admin_user: User, lead: User, django_capture_on_commit_callbacks: OnCommit
) -> None:
    from reviews.tests.factories import make_item

    real = make_item(lead)
    job_id = _client(admin_user).post("/api/imports/sample").json()["id"]
    with django_capture_on_commit_callbacks(execute=True):
        _client(admin_user).post(f"/api/imports/{job_id}/commit", {}, content_type="application/json")
    client = _client(lead)

    queue = client.get("/api/items").json()["rows"]
    assert [r["id"] for r in queue] == [real.pk]
    legacy_open = client.get("/api/items?is_legacy=true").json()["rows"]
    assert len(legacy_open) == 16
    assert client.get("/api/items/stats").json()["open"] == 1


def test_upload_reads_the_workbook(admin_user: User) -> None:
    upload = SimpleUploadedFile("tracker.xlsx", SAMPLE_TRACKER_PATH.read_bytes())

    response = _client(admin_user).post("/api/imports", {"file": upload})

    assert response.status_code == 201, response.content
    assert (response.json()["filename"], response.json()["row_count"]) == ("tracker.xlsx", 180)


@pytest.mark.parametrize("data", [b"PK...", b"Request ID,Status\nMCR-25-001,Approved\n"])
def test_upload_of_a_non_xlsx_file_is_a_field_error(admin_user: User, data: bytes) -> None:
    response = _client(admin_user).post("/api/imports", {"file": SimpleUploadedFile("tracker.xlsx", data)})

    assert response.status_code == 422, response.content
    body = response.json()
    assert body["code"] == "invalid_input"
    assert body["fields"][0]["loc"] == ["body", "file"]
    assert "isn't an .xlsx workbook" in body["message"]


@pytest.mark.parametrize("role", [Role.MARKETER, Role.REVIEWER, Role.LEAD])
def test_non_admins_get_403(user_factory: Callable[..., User], role: Role) -> None:
    client = _client(user_factory(roles=[role]))

    assert client.post("/api/imports/sample").status_code == 403
    assert client.get("/api/imports").status_code == 403


def test_bad_mapping_values_are_422(admin_user: User) -> None:
    client = _client(admin_user)
    job_id = client.post("/api/imports/sample").json()["id"]

    response = client.put(
        f"/api/imports/{job_id}/mapping",
        {"value_mappings": [{"field": "product", "source_value": "Auto", "value": "auto_loan"}]},
        content_type="application/json",
    )

    assert response.status_code == 422
    assert response.json()["fields"][0]["loc"] == ["body", "value_mappings", 0, "value"]


def test_unknown_import_is_404(admin_user: User) -> None:
    assert _client(admin_user).get("/api/imports/999999").status_code == 404


def test_list_imports_query_count_does_not_grow(admin_user: User) -> None:
    client = _client(admin_user)
    client.post("/api/imports/sample")

    def count() -> int:
        with CaptureQueriesContext(connection) as ctx:
            assert client.get("/api/imports").status_code == 200
        return len(ctx.captured_queries)

    small = count()
    client.post("/api/imports/sample")
    client.post("/api/imports/sample")
    assert count() == small
