"""Import services on real Postgres: the sample commits to exactly the README's totals, and commit is idempotent."""

from collections import Counter
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

import pytest

from accounts.models import User
from audit.models import Event
from audit.payloads import ItemImportedPayload, parse_payload
from core.clock import FixedClock
from core.domain import DecisionOutcome, EventType, ItemStatus, PartnerType, Product
from core.errors import Conflict, InvalidInput, NotPermitted
from imports import selectors, services
from imports.domain import ImportStatus, ImportTargetField, ImportValueField, RowAction
from imports.models import ImportJob, ImportRow
from imports.normalize import StatusOverride, ValueOverride
from partners.models import Partner
from reviews.models import ReviewItem
from reviews.tests.factories import make_partner

pytestmark = pytest.mark.django_db

type OnCommit = Callable[..., AbstractContextManager[list[Callable[[], Any]]]]


def _commit(admin: User, job_id: int, capture: OnCommit, clock: FixedClock, **kwargs: Any) -> None:
    with capture(execute=True):
        services.request_commit(actor=admin, job_id=job_id, clock=clock, **kwargs)


@pytest.fixture
def committed(admin_user: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit) -> int:
    job_id = services.create_sample_import(actor=admin_user, clock=clock)
    _commit(admin_user, job_id, django_capture_on_commit_callbacks, clock)
    return job_id


def _item(ref: str) -> ReviewItem:
    return ReviewItem.objects.select_related("partner").get(legacy_ref=ref)


def _imported_payloads() -> list[ItemImportedPayload]:
    out = []
    for event in Event.objects.filter(type=EventType.ITEM_IMPORTED.value):
        payload = parse_payload(EventType.ITEM_IMPORTED, event.payload)
        assert isinstance(payload, ItemImportedPayload)
        out.append(payload)
    return out


def test_sample_commit_matches_the_readme_totals(committed: int) -> None:
    job = ImportJob.objects.get(pk=committed)
    items = ReviewItem.objects.all()

    assert job.status == ImportStatus.COMMITTED.value
    assert (job.created_count, job.skipped_count, job.partners_created_count) == (178, 2, 8)
    assert items.count() == 178
    assert items.filter(is_legacy=True, owner__isnull=True, current_version__isnull=True).count() == 178
    assert items.filter(legacy_ref="MCR-26-101-b").exists()
    assert Counter(items.values_list("status", flat=True)) == {
        ItemStatus.APPROVED.value: 145,
        ItemStatus.CHANGES_REQUESTED.value: 11,
        ItemStatus.IN_REVIEW.value: 8,
        ItemStatus.REJECTED.value: 6,
        ItemStatus.SUBMITTED.value: 8,
    }
    open_items = items.filter(status__in=[ItemStatus.SUBMITTED.value, ItemStatus.IN_REVIEW.value])
    assert open_items.count() == 16
    assert open_items.filter(legacy_reviewer="").count() == 8
    assert ImportRow.objects.filter(job=job).count() == 180
    assert Partner.objects.count() == 8
    assert Event.objects.filter(type=EventType.PARTNER_CREATED.value).count() == 8
    assert Event.objects.filter(type=EventType.IMPORT_COMMITTED.value, entity_id=job.pk).count() == 1


def test_each_item_gets_an_imported_event_carrying_its_timeline(committed: int) -> None:
    payloads = _imported_payloads()
    outcomes = Counter(p.timeline.outcome for p in payloads)

    assert len(payloads) == 178
    assert {p.import_id for p in payloads} == {committed}
    assert outcomes == {
        DecisionOutcome.APPROVED: 132,
        DecisionOutcome.APPROVED_WITH_EDITS: 13,
        DecisionOutcome.CHANGES_REQUESTED: 11,
        DecisionOutcome.REJECTED: 6,
        None: 16,
    }
    events = Event.objects.filter(type=EventType.ITEM_IMPORTED.value).values_list("item", "entity_id", "to_status")
    statuses = dict(ReviewItem.objects.values_list("pk", "status"))
    assert all(item == entity and to_status == statuses[item] for item, entity, to_status in events)

    r13 = next(p for p in payloads if p.legacy_ref == "MCR-25-012")
    assert r13.row_number == 13
    assert r13.timeline.submitted_at == datetime(2025, 12, 5, tzinfo=UTC)
    assert r13.timeline.first_reviewed_at == datetime(2025, 12, 17, tzinfo=UTC)
    assert r13.timeline.decided_at == datetime(2026, 1, 15, tzinfo=UTC)
    assert r13.timeline.rounds == 4


def test_legacy_item_fields(committed: int) -> None:
    del committed
    r13 = _item("MCR-25-012")  # approver only, blank expiry
    r34 = _item("MCR-26-015")  # blank status, text expiry
    r70 = _item("MCR-26-050")  # "CardPerks"

    assert (r13.status, r13.product, r13.risk_tier) == ("approved", Product.MORTGAGE_PREQUAL.value, "high")
    assert r13.approved_at == datetime(2026, 1, 15, tzinfo=UTC)
    assert r13.approval_expires_at is None
    assert "Approved by Leah Brandt (date from the last round)." in r13.notes
    assert r13.legacy_submitter == "Elena Ruiz / Mortgage Marketing"
    assert r13.legacy_reviewer == "Leah Brandt"
    assert r13.legacy_history.startswith("R1 12/17 LB:")
    assert r13.source_url.startswith("https://sharepoint.clearpath.example/")
    assert r13.round == 4
    assert r13.llm_check_status == "skipped"
    assert r34.status == "approved"
    assert r34.approval_expires_at == datetime(2026, 3, 12, tzinfo=UTC)
    assert r70.partner is not None
    assert r70.partner.name == "CardPerks Weekly"
    assert r70.partner.type == PartnerType.AFFILIATE.value


def test_recommitting_a_committed_job_does_nothing(
    committed: int, admin_user: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    _commit(admin_user, committed, django_capture_on_commit_callbacks, clock)
    services.commit_import(job_id=committed, clock=clock)  # a duplicate delivery of the task

    assert ReviewItem.objects.count() == 178
    assert Event.objects.filter(type=EventType.ITEM_IMPORTED.value).count() == 178
    assert ImportRow.objects.count() == 180


def test_importing_the_same_file_again_creates_nothing(
    committed: int, admin_user: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    del committed
    second = services.create_sample_import(actor=admin_user, clock=clock)

    preview = selectors.get_preview(viewer=admin_user, job_id=second)
    assert (preview.counts.ready, preview.counts.already_imported) == (0, 178)

    _commit(admin_user, second, django_capture_on_commit_callbacks, clock)
    job = ImportJob.objects.get(pk=second)
    assert (job.status, job.created_count, job.partners_created_count) == ("committed", 0, 0)
    assert ReviewItem.objects.count() == 178


def test_committed_preview_shows_what_commit_did(committed: int, admin_user: User) -> None:
    preview = selectors.get_preview(viewer=admin_user, job_id=committed)

    assert preview.status is ImportStatus.COMMITTED
    assert (preview.counts.rows_total, preview.counts.ready) == (180, 178)
    assert {r.action for r in preview.rows if r.row_number in {19, 68}} == {
        RowAction.SKIP_NOT_DATA,
        RowAction.SKIP_DUPLICATE,
    }


def test_committed_preview_links_each_created_row_to_its_item(committed: int, admin_user: User) -> None:
    preview = selectors.get_preview(viewer=admin_user, job_id=committed)

    created = [r for r in preview.rows if r.action is RowAction.CREATE]
    assert len(created) == 178
    items = {i.pk: i.legacy_ref for i in ReviewItem.objects.only("legacy_ref")}
    assert all(r.item_id is not None and items[r.item_id] == r.legacy_ref for r in created)
    assert all(r.item_id is None for r in preview.rows if r.action is not RowAction.CREATE)


def test_committed_preview_reads_item_ids_in_one_query(
    committed: int, admin_user: User, django_assert_max_num_queries: Callable[..., AbstractContextManager[Any]]
) -> None:
    with django_assert_max_num_queries(3):  # the job, its stored rows, nothing per row
        selectors.get_preview(viewer=admin_user, job_id=committed)


def test_preview_before_commit_has_no_item_ids(admin_user: User, clock: FixedClock) -> None:
    job_id = services.create_sample_import(actor=admin_user, clock=clock)

    preview = selectors.get_preview(viewer=admin_user, job_id=job_id)

    assert preview.rows
    assert all(r.item_id is None for r in preview.rows)


@pytest.mark.parametrize("app_spelling", ["lendcompare", "Lend Compare", "Lend-Compare"])
def test_existing_partners_are_reused_not_duplicated(
    admin_user: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit, app_spelling: str
) -> None:
    existing = make_partner(app_spelling)
    job_id = services.create_sample_import(actor=admin_user, clock=clock)

    _commit(admin_user, job_id, django_capture_on_commit_callbacks, clock)

    assert Partner.objects.count() == 8
    assert ImportJob.objects.get(pk=job_id).partners_created_count == 7
    for ref in ("MCR-26-022", "MCR-26-136"):  # "Lend Compare" in the sheet
        partner = _item(ref).partner
        assert partner is not None
        assert partner.pk == existing.pk


def test_a_columns_only_update_keeps_saved_status_and_value_mappings(admin_user: User, clock: FixedClock) -> None:
    job_id = services.create_sample_import(actor=admin_user, clock=clock)
    services.set_mapping(
        actor=admin_user,
        job_id=job_id,
        update=services.MappingUpdate(
            statuses=(StatusOverride("Done", ItemStatus.APPROVED, None),),
            values=(ValueOverride(ImportValueField.PRODUCT, "Auto", "personal_loan"),),
        ),
        clock=clock,
    )

    services.set_mapping(
        actor=admin_user,
        job_id=job_id,
        update=services.MappingUpdate(columns={"Live URL / Placement & Screenshot Link": ImportTargetField.IGNORE}),
        clock=clock,
    )

    job = ImportJob.objects.get(pk=job_id)
    assert [s["source_value"] for s in job.status_mapping] == ["Done"]
    assert [v["source_value"] for v in job.value_mapping] == ["Auto"]
    assert job.column_mapping["Live URL / Placement & Screenshot Link"] == "ignore"


def test_two_columns_can_not_map_to_one_field(admin_user: User, clock: FixedClock) -> None:
    job_id = services.create_sample_import(actor=admin_user, clock=clock)

    with pytest.raises(InvalidInput, match="Status is mapped from both 'Revision Round' and 'Status'"):
        services.set_mapping(
            actor=admin_user,
            job_id=job_id,
            update=services.MappingUpdate(columns={"Revision Round": ImportTargetField.STATUS}),
            clock=clock,
        )


def test_only_admins_import(user_factory: Callable[..., User], clock: FixedClock) -> None:
    from core.domain import Role

    for role in (Role.MARKETER, Role.REVIEWER, Role.LEAD):
        user = user_factory(roles=[role])
        with pytest.raises(NotPermitted):
            services.create_sample_import(actor=user, clock=clock)
        with pytest.raises(NotPermitted):
            selectors.list_imports(viewer=user)


def test_mapping_is_validated(admin_user: User, clock: FixedClock) -> None:
    job_id = services.create_sample_import(actor=admin_user, clock=clock)

    def set_(**kwargs: Any) -> None:
        services.set_mapping(actor=admin_user, job_id=job_id, update=services.MappingUpdate(**kwargs), clock=clock)

    with pytest.raises(InvalidInput, match="no column 'Nope'"):
        set_(columns={"Nope": ImportTargetField.STATUS})
    with pytest.raises(InvalidInput, match="can't be needs rereview"):
        set_(columns={}, statuses=(StatusOverride("On hold", ItemStatus.NEEDS_REREVIEW, None),))
    with pytest.raises(InvalidInput, match="can't have that decision"):
        set_(columns={}, statuses=(StatusOverride("Done", ItemStatus.APPROVED, DecisionOutcome.REJECTED),))
    with pytest.raises(InvalidInput, match="isn't a valid Partner"):
        set_(columns={}, values=(ValueOverride(ImportValueField.PARTNER, "Blog", "No Such Partner"),))

    set_(columns={}, statuses=(StatusOverride("Done", ItemStatus.APPROVED, None),))
    detail = selectors.get_import(viewer=admin_user, job_id=job_id)
    assert detail.status is ImportStatus.MAPPED
    assert ImportJob.objects.get(pk=job_id).status_mapping == [
        {"source_value": "Done", "status": "approved", "outcome": "approved"}
    ]


def test_status_values_list_every_distinct_value_with_its_mapping(admin_user: User, clock: FixedClock) -> None:
    job_id = services.create_sample_import(actor=admin_user, clock=clock)

    values = {v.source_value: v for v in selectors.get_import(viewer=admin_user, job_id=job_id).status_values}

    assert len(values) == 13
    assert values["Needs changes"].status is ItemStatus.CHANGES_REQUESTED
    assert values["Needs changes"].source == "default"
    assert values["Approved - minor edits"].outcome is DecisionOutcome.APPROVED_WITH_EDITS


def test_mapping_can_not_change_after_commit(committed: int, admin_user: User, clock: FixedClock) -> None:
    with pytest.raises(Conflict, match="committed"):
        services.set_mapping(actor=admin_user, job_id=committed, update=services.MappingUpdate(), clock=clock)


def test_commit_refuses_a_missing_required_mapping(admin_user: User, clock: FixedClock) -> None:
    job_id = services.create_sample_import(actor=admin_user, clock=clock)
    services.set_mapping(
        actor=admin_user,
        job_id=job_id,
        update=services.MappingUpdate(columns={"Request ID": ImportTargetField.IGNORE}),
        clock=clock,
    )

    with pytest.raises(Conflict, match="Map a column to Request ID"):
        services.request_commit(actor=admin_user, job_id=job_id, clock=clock)


def test_commit_refuses_blocked_rows_unless_skipping(
    admin_user: User, clock: FixedClock, django_capture_on_commit_callbacks: OnCommit
) -> None:
    job_id = services.create_sample_import(actor=admin_user, clock=clock)
    job = ImportJob.objects.get(pk=job_id)
    job.workbook["tracker"]["rows"][0]["cells"][12] = {"text": "On hold"}  # r2's Status
    job.save()

    with pytest.raises(Conflict, match="1 row has problems"):
        services.request_commit(actor=admin_user, job_id=job_id, skip_blocked=False, clock=clock)

    _commit(admin_user, job_id, django_capture_on_commit_callbacks, clock, skip_blocked=True)
    assert ReviewItem.objects.count() == 177
    assert not ReviewItem.objects.filter(legacy_ref="MCR-25-001").exists()
    assert ImportRow.objects.get(job_id=job_id, row_number=2).action == RowAction.BLOCKED.value


def test_a_failed_commit_rolls_back_and_can_be_retried(
    admin_user: User,
    clock: FixedClock,
    django_capture_on_commit_callbacks: OnCommit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = services.create_sample_import(actor=admin_user, clock=clock)
    real = services._create_item
    calls = Counter[str]()

    def flaky(row: Any, **kwargs: Any) -> ReviewItem:
        calls["n"] += 1
        if calls["n"] == 100:
            raise RuntimeError("disk full")
        return real(row, **kwargs)

    monkeypatch.setattr(services, "_create_item", flaky)
    _commit(admin_user, job_id, django_capture_on_commit_callbacks, clock)

    job = ImportJob.objects.get(pk=job_id)
    assert job.status == ImportStatus.FAILED.value
    assert (
        job.error
        == f"The commit failed and nothing was imported. Try again; if it fails again, report import {job_id}."
    )
    assert "disk full" not in job.error  # internals stay in the log
    assert ReviewItem.objects.count() == 0
    assert Partner.objects.count() == 0

    monkeypatch.setattr(services, "_create_item", real)
    _commit(admin_user, job_id, django_capture_on_commit_callbacks, clock)
    assert ImportJob.objects.get(pk=job_id).status == ImportStatus.COMMITTED.value
    assert ReviewItem.objects.count() == 178
