"""Export jobs and evidence packs on real Postgres, through services and HTTP."""

import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import timedelta
from typing import Any

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from accounts.models import User
from audit.models import Event
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import AttachmentKind, EventType, ItemStatus, Role
from core.errors import Conflict, InvalidInput, NotPermitted
from exports import evidence, services
from exports.domain import ExportStatus
from exports.models import ExportJob
from exports.tests.conftest import APPROVED_TEXT, Approved
from reviews.filters import ItemFilter, ItemSort
from reviews.models import Attachment, DecisionEvidence
from reviews.services import AttachmentOwner, add_attachment
from reviews.tests.factories import make_item, make_partner

pytestmark = pytest.mark.django_db

type OnCommit = Callable[..., AbstractContextManager[list[Callable[[], Any]]]]


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _file(job_id: int) -> bytes:
    job = ExportJob.objects.get(pk=job_id)
    assert job.status == ExportStatus.READY.value, job.error
    with job.file.open("rb") as f:
        return f.read()


def _sheet(data: bytes) -> list[tuple[object, ...]]:
    ws = openpyxl.load_workbook(io.BytesIO(data))["Items"]
    return [tuple(c.value for c in r) for r in ws.iter_rows()]


def _verify_sha256sums(zf: zipfile.ZipFile, prefix: str = "") -> list[str]:
    lines = zf.read(f"{prefix}SHA256SUMS").decode().splitlines()
    paths = []
    for line in lines:
        digest, path = line.split("  ", 1)
        assert hashlib.sha256(zf.read(prefix + path)).hexdigest() == digest, path
        paths.append(path)
    return paths


# --- items xlsx ------------------------------------------------------------------------------------------------


def test_export_writes_the_filtered_view(
    reviewer: User, marketer: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    make_item(marketer, title="Mine", assignee=reviewer)
    make_item(marketer, title="Someone else's")

    with django_capture_on_commit_callbacks(execute=True):
        job_id = services.request_export(actor=reviewer, filters=ItemFilter(mine=True), clock=clock)

    rows = _sheet(_file(job_id))
    assert [r[1] for r in rows[1:]] == ["Mine"]  # `mine` is relative to the requester
    job = ExportJob.objects.get(pk=job_id)
    assert (job.item_count, job.filename) == (1, "clearpath-items-2026-10-24.xlsx")
    event = Event.objects.get(type=EventType.EXPORT_CREATED.value, entity_id=job_id)
    assert event.payload == {"export_id": job_id, "item_count": 1}
    assert event.actor_id == reviewer.pk  # pyrefly: ignore[missing-attribute]


def test_export_follows_the_view_sort(
    lead: User, marketer: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    for title in ("Beta", "Alpha", "Gamma"):
        make_item(marketer, title=title)

    with django_capture_on_commit_callbacks(execute=True):
        job_id = services.request_export(actor=lead, filters=ItemFilter(), sort=ItemSort.TITLE, clock=clock)

    assert [r[1] for r in _sheet(_file(job_id))[1:]] == ["Alpha", "Beta", "Gamma"]


def test_marketers_cannot_export_views(marketer: User, clock: FixedClock) -> None:
    with pytest.raises(NotPermitted):
        services.request_export(actor=marketer, filters=ItemFilter(), clock=clock)


def test_imported_legacy_items_export_with_tracker_people(
    admin_user: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    from imports import services as imports

    with django_capture_on_commit_callbacks(execute=True):
        imports.request_commit(actor=admin_user, job_id=imports.create_sample_import(actor=admin_user, clock=clock))
    with django_capture_on_commit_callbacks(execute=True):
        job_id = services.request_export(
            actor=admin_user, filters=ItemFilter(is_legacy=True, status=[ItemStatus.APPROVED]), clock=clock
        )

    rows = {r[17]: r for r in _sheet(_file(job_id))[1:]}
    assert len(rows) == 145
    r13 = rows["MCR-25-012"]
    assert (r13[2], r13[3], r13[11], r13[12]) == (
        "Approved",
        "Mortgage prequal",
        "Elena Ruiz / Mortgage Marketing",
        "Leah Brandt",
    )


def test_a_failed_build_is_recorded_on_the_job(
    lead: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> int:
        raise OSError("storage unavailable")

    monkeypatch.setattr(services, "write_items_xlsx", broken)
    with django_capture_on_commit_callbacks(execute=True):
        job_id = services.request_export(actor=lead, filters=ItemFilter(), clock=clock)

    job = ExportJob.objects.get(pk=job_id)
    assert job.status == ExportStatus.FAILED.value
    assert job.error == f"The export failed. Request it again; if it fails again, report export {job_id}."
    assert not Event.objects.filter(type=EventType.EXPORT_CREATED.value).exists()


def test_a_job_runs_once(lead: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        job_id = services.request_export(actor=lead, filters=ItemFilter(), clock=clock)
    services.run_export(job_id=job_id, clock=clock)  # a duplicate delivery

    assert Event.objects.filter(type=EventType.EXPORT_CREATED.value).count() == 1


# --- evidence packs --------------------------------------------------------------------------------------------


def test_evidence_pack_record(approved: Approved, clock: FixedClock) -> None:
    pack = evidence.evidence_pack(item_id=approved.item.pk, clock=clock)

    assert pack.decision.id == approved.decision.pk
    assert (pack.approved_version.n, pack.approved_version.content_text) == (2, APPROVED_TEXT)
    assert [(t.product.value, t.version) for t in pack.offer_terms] == [("personal_loan", 7)]
    assert [f.reason for f in pack.findings] == ["Range is in the footer."]
    assert [e.attachment_id for e in pack.evidence] == [approved.attachment_id]


def test_evidence_pack_zip_verifies(
    approved: Approved, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        job_id = services.request_evidence_pack(actor=approved.marketer, item_id=approved.item.pk, clock=clock)

    zf = zipfile.ZipFile(io.BytesIO(_file(job_id)))
    paths = _verify_sha256sums(zf)
    evidence_path = f"evidence/{approved.attachment_id}-rate_sheet_Q4_.pdf"
    assert sorted(paths) == sorted(
        [
            "approved-version-v2.txt",
            "decision.json",
            evidence_path,
            "history.json",
            "manifest.json",
            "offer-terms/personal_loan-v7.json",
            "summary.txt",
        ]
    )
    assert zf.read("approved-version-v2.txt").decode() == APPROVED_TEXT
    assert zf.read(evidence_path) == b"%PDF rate sheet"
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["approved_version"]["matches_recorded"] is True
    assert [e["matches_decision"] for e in manifest["evidence"]] == [True]
    terms = json.loads(zf.read("offer-terms/personal_loan-v7.json"))
    assert terms["offer_terms"]["values"]["apr_min"] == "7.49"
    assert terms["quoted_in_approved_version"][0]["quote"] == "7.49%"
    decision = json.loads(zf.read("decision.json"))
    assert (decision["decision_label"], decision["findings"][0]["state"]) == ("Approve", "dismissed")
    assert "attachment.added" in {e["type"] for e in json.loads(zf.read("history.json"))}
    summary = zf.read("summary.txt").decode()
    assert "Decision:         Approve (Standard review) by Dana Kim" in summary
    assert ExportJob.objects.get(pk=job_id).filename == f"CP-{approved.item.pk}-evidence-pack-2026-10-24.zip"


def test_evidence_pack_flags_a_file_that_changed_since_the_decision(
    approved: Approved, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    attachment = Attachment.objects.get(pk=approved.attachment_id)
    with open(attachment.file.path, "wb") as f:  # noqa: PTH123  # tampering with the stored file
        f.write(b"%PDF edited later")

    with django_capture_on_commit_callbacks(execute=True):
        job_id = services.request_evidence_pack(actor=approved.reviewer, item_id=approved.item.pk, clock=clock)

    zf = zipfile.ZipFile(io.BytesIO(_file(job_id)))
    (row,) = json.loads(zf.read("manifest.json"))["evidence"]
    assert row["matches_decision"] is False
    assert row["sha256"] == hashlib.sha256(b"%PDF edited later").hexdigest()
    assert "1 no longer match the hash recorded at decision" in zf.read("summary.txt").decode()


def test_evidence_pack_needs_an_approval(marketer: User, clock: FixedClock) -> None:
    pending = make_item(marketer)
    legacy = make_item(None, is_legacy=True, legacy_ref="MCR-26-001", status=ItemStatus.APPROVED)

    with pytest.raises(Conflict, match="has no approval yet"):
        services.request_evidence_pack(actor=marketer, item_id=pending.pk, clock=clock)
    with pytest.raises(Conflict, match="legacy import with no decision record"):
        evidence.evidence_pack(item_id=legacy.pk, clock=clock)


def test_view_export_can_bundle_evidence_packs(
    approved: Approved, lead: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    make_item(approved.marketer, title="Not approved")

    with django_capture_on_commit_callbacks(execute=True):
        job_id = services.request_export(actor=lead, filters=ItemFilter(), include_evidence_packs=True, clock=clock)

    zf = zipfile.ZipFile(io.BytesIO(_file(job_id)))
    assert len(_sheet(zf.read("items.xlsx"))) == 3
    prefix = f"evidence-packs/CP-{approved.item.pk}/"
    assert "approved-version-v2.txt" in _verify_sha256sums(zf, prefix)
    assert {n.split("/")[1] for n in zf.namelist() if n.startswith("evidence-packs/")} == {f"CP-{approved.item.pk}"}


def test_bundled_packs_are_capped(
    approved: Approved, lead: User, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    del approved
    monkeypatch.setattr(services, "MAX_EVIDENCE_PACKS", 0)

    with pytest.raises(InvalidInput, match="1 items in this view have approvals"):
        services.request_export(actor=lead, filters=ItemFilter(), include_evidence_packs=True, clock=clock)


# --- HTTP ------------------------------------------------------------------------------------------------------


def test_export_over_http(
    reviewer: User, user_factory: UserFactory, marketer: User, django_capture_on_commit_callbacks: OnCommit
) -> None:
    make_item(marketer)
    client = _client(reviewer)

    with django_capture_on_commit_callbacks(execute=True):
        created = client.post("/api/exports", {"filters": {"status": ["submitted"]}}, content_type="application/json")
    assert created.status_code == 202, created.content
    export_id = created.json()["id"]

    status = client.get(f"/api/exports/{export_id}").json()
    assert (status["status"], status["item_count"], status["kind"]) == ("ready", 1, "items_xlsx")
    download = client.get(status["download_url"])
    assert download.status_code == 200
    assert download["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert 'filename="clearpath-items-' in download["Content-Disposition"]
    assert len(_sheet(b"".join(download.streaming_content))) == 2  # pyrefly: ignore[missing-attribute]

    other = _client(user_factory(roles=[Role.REVIEWER]))
    assert other.get(f"/api/exports/{export_id}").status_code == 404
    assert other.get(status["download_url"]).status_code == 404
    assert _client(user_factory(roles=[Role.ADMIN])).get(status["download_url"]).status_code == 200
    assert _client(marketer).post("/api/exports", {}, content_type="application/json").status_code == 403


def test_download_before_ready_is_409(lead: User, clock: FixedClock) -> None:
    job_id = services.request_export(actor=lead, filters=ItemFilter(), clock=clock)  # on_commit never runs

    response = _client(lead).get(f"/api/exports/{job_id}/download")

    assert response.status_code == 409
    assert ExportJob.objects.get(pk=job_id).status == ExportStatus.PENDING.value


def test_evidence_pack_over_http(approved: Approved, django_capture_on_commit_callbacks: OnCommit) -> None:
    client = _client(approved.marketer)  # anyone who can read the item

    record = client.get(f"/api/items/{approved.item.pk}/evidence-pack")
    assert record.status_code == 200, record.content
    body = record.json()
    assert (body["decision"]["id"], body["approved_version"]["n"]) == (approved.decision.pk, 2)
    assert body["offer_terms"][0]["version"] == 7
    assert body["findings"][0]["reason"] == "Range is in the footer."

    with django_capture_on_commit_callbacks(execute=True):
        created = client.post(f"/api/items/{approved.item.pk}/evidence-pack")
    assert created.status_code == 202, created.content
    status = client.get(f"/api/exports/{created.json()['id']}").json()
    assert (status["kind"], status["item_id"], status["status"]) == ("evidence_pack", approved.item.pk, "ready")
    download = client.get(status["download_url"])
    assert download["Content-Type"] == "application/zip"


def test_evidence_pack_for_an_unapproved_item_is_409(marketer: User) -> None:
    item = make_item(marketer)
    client = _client(marketer)

    assert client.get(f"/api/items/{item.pk}/evidence-pack").status_code == 409
    assert client.post(f"/api/items/{item.pk}/evidence-pack").json()["code"] == "conflict"
    assert client.get("/api/items/999999/evidence-pack").status_code == 404


def test_partner_documents_are_withheld_from_a_marketers_pack(
    approved: Approved, lead: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    partner = make_partner("LendCompare")
    agreement = add_attachment(
        actor=lead,
        owner=AttachmentOwner(kind="partner", id=partner.pk),
        kind=AttachmentKind.AGREEMENT,
        file=SimpleUploadedFile("agreement.pdf", b"%PDF agreement", content_type="application/pdf"),
        clock=clock,
    )
    DecisionEvidence.objects.create(decision=approved.decision, attachment_id=agreement.id, sha256=agreement.sha256)

    def pack_for(user: User) -> zipfile.ZipFile:
        with django_capture_on_commit_callbacks(execute=True):
            job_id = services.request_evidence_pack(actor=user, item_id=approved.item.pk, clock=clock)
        return zipfile.ZipFile(io.BytesIO(_file(job_id)))

    marketers = pack_for(approved.marketer)
    rows = {e["attachment_id"]: e for e in json.loads(marketers.read("manifest.json"))["evidence"]}
    assert rows[agreement.id]["withheld"]
    assert rows[agreement.id]["sha256_at_decision"] == agreement.sha256
    assert not [n for n in marketers.namelist() if "agreement" in n]
    assert rows[approved.attachment_id]["withheld"] is None  # the item's own evidence is still there
    _verify_sha256sums(marketers)

    reviewers = pack_for(approved.reviewer)
    assert f"evidence/{agreement.id}-agreement.pdf" in reviewers.namelist()


def test_a_running_export_whose_worker_died_is_reclaimed(
    lead: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    job_id = services.request_export(actor=lead, filters=ItemFilter(), clock=clock)  # enqueue never runs
    ExportJob.objects.filter(pk=job_id).update(status=ExportStatus.RUNNING.value, started_at=clock.now())

    services.run_export(job_id=job_id, clock=clock)  # a fresh run: someone else is on it
    assert ExportJob.objects.get(pk=job_id).status == ExportStatus.RUNNING.value

    clock.advance(timedelta(minutes=10))
    services.run_export(job_id=job_id, clock=clock)  # the redelivered message after the worker died
    assert ExportJob.objects.get(pk=job_id).status == ExportStatus.READY.value
