"""Every file path the app has (attachments, imports, exports, evidence packs) on production's S3 storage (moto), over
HTTP: written to the private bucket, read back only through the permission-checked download endpoints."""

import hashlib
import io
import zipfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from accounts.models import User
from conftest import UserFactory
from core.domain import Role
from exports.models import ExportJob
from exports.tests.conftest import Approved
from imports.models import ImportJob
from imports.workbook import SAMPLE_TRACKER_PATH
from reviews.models import Attachment
from reviews.tests.factories import make_item

pytestmark = pytest.mark.django_db

type OnCommit = Callable[..., AbstractContextManager[list[Callable[[], Any]]]]


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _body(response: Any) -> bytes:  # FileResponse
    return b"".join(response.streaming_content)


def _is_private(obj: Any) -> bool:  # boto3 Object
    grants = obj.Acl().grants
    return all(g["Grantee"].get("Type") == "CanonicalUser" for g in grants)


def test_attachments_round_trip_through_the_bucket_and_never_overwrite(
    s3_bucket: Any,
    marketer: User,
    user_factory: UserFactory,
) -> None:
    item = make_item(marketer)
    client = _client(marketer)
    first = client.post(
        f"/api/items/{item.pk}/attachments",
        {"kind": "substantiation", "file": SimpleUploadedFile("memo.pdf", b"first memo", "application/pdf")},
    )
    second = client.post(
        f"/api/items/{item.pk}/attachments",
        {"kind": "substantiation", "file": SimpleUploadedFile("memo.pdf", b"second memo", "application/pdf")},
    )
    assert (first.status_code, second.status_code) == (201, 201), (first.content, second.content)

    a, b = (Attachment.objects.get(pk=r.json()["id"]) for r in (first, second))
    keys = {o.key for o in s3_bucket.objects.all()}
    # Same original name, same month: two objects. S3Storage's default (file_overwrite=True) would make the
    # second upload replace the first's bytes under the first row's sha256.
    assert a.file.name != b.file.name
    assert {a.file.name, b.file.name} <= keys
    assert all(_is_private(s3_bucket.Object(k)) for k in keys)

    download = _client(user_factory(roles=[Role.REVIEWER])).get(first.json()["download_url"])
    assert download.status_code == 200
    assert _body(download) == b"first memo"
    assert hashlib.sha256(b"first memo").hexdigest() == a.sha256
    assert 'filename="memo.pdf"' in download["Content-Disposition"]
    assert Client().get(first.json()["download_url"]).status_code == 401


def test_import_upload_keeps_the_workbook_in_the_bucket(s3_bucket: Any, admin_user: User) -> None:
    data = SAMPLE_TRACKER_PATH.read_bytes()

    response = _client(admin_user).post("/api/imports", {"file": SimpleUploadedFile("tracker.xlsx", data)})

    assert response.status_code == 201, response.content
    job = ImportJob.objects.get(pk=response.json()["id"])
    assert s3_bucket.Object(job.file.name).get()["Body"].read() == data


def test_evidence_pack_reads_evidence_from_and_writes_the_zip_to_the_bucket(
    s3_bucket: Any,
    approved: Approved,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    client = _client(approved.marketer)

    with django_capture_on_commit_callbacks(execute=True):
        created = client.post(f"/api/items/{approved.item.pk}/evidence-pack")
    assert created.status_code == 202, created.content
    status = client.get(f"/api/exports/{created.json()['id']}").json()
    assert status["status"] == "ready", status
    download = client.get(status["download_url"])

    assert download.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(_body(download)))
    assert zf.read(f"evidence/{approved.attachment_id}-rate_sheet_Q4_.pdf") == b"%PDF rate sheet"
    job = ExportJob.objects.get(pk=created.json()["id"])
    assert job.file.name in {o.key for o in s3_bucket.objects.all()}


def test_view_export_lands_in_the_bucket(
    s3_bucket: Any,
    reviewer: User,
    marketer: User,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    make_item(marketer)
    client = _client(reviewer)

    with django_capture_on_commit_callbacks(execute=True):
        created = client.post("/api/exports", {"filters": {"status": ["submitted"]}}, content_type="application/json")
    status = client.get(f"/api/exports/{created.json()['id']}").json()
    download = client.get(status["download_url"])

    assert download.status_code == 200
    stored = s3_bucket.Object(ExportJob.objects.get(pk=created.json()["id"]).file.name).get()["Body"].read()
    assert _body(download) == stored
