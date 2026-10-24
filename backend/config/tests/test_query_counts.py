"""Every real read endpoint costs the same number of queries whatever the data size (no N+1).

Each case measures the endpoint, grows every kind of row it lists, and measures again. Comparing two sizes
catches a per-row query without pinning an absolute count that churns with unrelated changes.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from itertools import count
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test import Client
from django.test.utils import CaptureQueriesContext
from pytest_django import Settings

from accounts.models import User
from checks.models import Finding
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import (
    AttachmentKind,
    DecisionLane,
    DecisionOutcome,
    FindingSource,
    ItemStatus,
    NotificationKind,
    PersonalLoanTerms,
    Product,
    RiskTier,
    Role,
    Severity,
)
from notifications.models import Notification, OutboxEmail
from partners.models import Partner
from reviews.filters import ItemFilter, ItemSort
from reviews.models import Decision, Placement, ReviewItem, Version
from reviews.services import (
    AttachmentOwner,
    ItemFieldChanges,
    NewComment,
    NewSavedView,
    add_attachment,
    add_comment,
    create_saved_view,
    update_item_fields,
)
from reviews.tests.factories import AT, make_item, make_partner, make_version
from terms.models import OfferTerms

PHRASE = "no hard credit pull"
PL = PersonalLoanTerms(
    apr_min=Decimal("7.49"),
    apr_max=Decimal("35.99"),
    amount_min=Decimal(1000),
    amount_max=Decimal(50000),
    term_months=(24, 36, 60),
    origination_fee_min_pct=Decimal(0),
    origination_fee_max_pct=Decimal(8),
)


@dataclass
class World:
    lead: User
    marketer: User
    target: ReviewItem
    first_version: Version
    partner: Partner
    clock: FixedClock
    user_factory: UserFactory
    serial: count

    def grow(self, k: int) -> None:
        for _ in range(k):
            self._unit(next(self.serial))

    def _unit(self, n: int) -> None:  # one row of every listed kind
        at = AT + timedelta(hours=n)
        reviewer = self.user_factory(roles=[Role.REVIEWER])
        partner = make_partner(f"Partner {n}")

        queued = make_item(self.marketer, assignee=reviewer, partner=partner, risk_tier=RiskTier.HIGH)
        make_version(queued)

        approved = make_item(
            self.marketer, partner=partner, assignee=reviewer, status=ItemStatus.APPROVED, approved_at=at
        )
        approved_version = make_version(approved, f"Checking your rate: {PHRASE}. Offer {n}.")
        self._decide(approved, approved_version, reviewer, at)

        version = make_version(self.target, f"Revision {n}: {PHRASE}.", n=n + 1)
        self._decide(self.target, version, reviewer, at)
        Placement.objects.create(
            item=self.target,
            approved_version=version,
            location=f"Placement {n}",
            first_run=at.date(),
            created_by=self.marketer,
            created_at=at,
        )
        Finding.objects.create(
            version=self.first_version,
            rule_id=f"R{n}",
            citation="12 CFR 1026.24",
            source=FindingSource.CODE,
            severity=Severity.BLOCKING,
            message="Trigger term without disclosures.",
            created_at=at,
        )
        add_comment(
            actor=self.lead,
            item_id=self.target.pk,
            data=NewComment(body=f"Comment {n}", mention_user_ids=(reviewer.pk,)),
            clock=self.clock,
        )
        update_item_fields(
            actor=self.lead, item_id=self.target.pk, changes=ItemFieldChanges(tags=(f"t{n}",)), clock=self.clock
        )
        for owner in (
            AttachmentOwner(kind="item", id=self.target.pk),
            AttachmentOwner(kind="partner", id=self.partner.pk),
        ):
            add_attachment(
                actor=self.lead,
                owner=owner,
                kind=AttachmentKind.SUBSTANTIATION,
                file=SimpleUploadedFile(f"memo{n}.pdf", f"memo {n}".encode(), content_type="application/pdf"),
                clock=self.clock,
            )
        create_saved_view(
            actor=self.lead,
            data=NewSavedView(name=f"View {n}", filters=ItemFilter(), sort=ItemSort.QUEUE),
            clock=self.clock,
        )
        Notification.objects.create(
            user=self.lead, kind=NotificationKind.MENTION, item=self.target, message=f"Mention {n}", created_at=at
        )
        OutboxEmail.objects.create(
            to=["partner@example.com"],
            subject=f"Email {n}",
            body="Body",
            item=self.target,
            requested_by=self.lead,
            approved_by=self.lead,
            sent_at=at,
        )
        OfferTerms.objects.create(
            product=Product.PERSONAL_LOAN,
            version=n,
            effective_range=DateTimeTZRange(AT - timedelta(days=n + 1), AT - timedelta(days=n), "[)"),
            values=PL.model_dump(mode="json"),
            created_by=self.lead,
            created_at=at,
        )

    def _decide(self, item: ReviewItem, version: Version, approver: User, at: object) -> None:
        Decision.objects.create(
            item=item,
            version=version,
            outcome=DecisionOutcome.APPROVED,
            lane=DecisionLane.STANDARD,
            approver=approver,
            reason="Disclosures present.",
            ruleset_date=AT.date(),
            expires_at=AT + timedelta(days=365),
            decided_at=at,
        )


@pytest.fixture
def world(user_factory: UserFactory, marketer: User, clock: FixedClock, settings: Settings, tmp_path: Path) -> World:
    settings.MEDIA_ROOT = tmp_path
    lead = user_factory(roles=[Role.LEAD])
    target = make_item(marketer, status=ItemStatus.IN_REVIEW)
    first_version = make_version(target, f"Original: {PHRASE}.")
    ReviewItem.objects.filter(pk=target.pk).update(current_version=first_version)
    world = World(
        lead=lead,
        marketer=marketer,
        target=target,
        first_version=first_version,
        partner=make_partner("Fixed partner"),
        clock=clock,
        user_factory=user_factory,
        serial=count(1),
    )
    OfferTerms.objects.create(
        product=Product.PERSONAL_LOAN,
        version=1000,
        effective_range=DateTimeTZRange(AT, None, "[)"),
        values=PL.model_dump(mode="json"),
        created_by=lead,
        created_at=AT,
    )
    return world


READS = [
    ("getMe", "/api/me"),
    ("listUsers", "/api/users"),
    ("listItems", "/api/items"),
    ("listItems(updated)", "/api/items?sort=updated&status=submitted&status=in_review&status=approved"),
    ("getQueueStats", "/api/items/stats"),
    ("getItem", "/api/items/{item}"),
    ("listVersions", "/api/items/{item}/versions"),
    ("getItemHistory", "/api/items/{item}/history"),
    ("listComments", "/api/items/{item}/comments"),
    ("listAttachments", "/api/items/{item}/attachments"),
    ("listPlacements", "/api/items/{item}/placements"),
    ("listDecisions", "/api/items/{item}/decisions"),
    ("listFindings", "/api/items/{item}/findings"),
    ("listSavedViews", "/api/views"),
    ("listLibrary", "/api/library"),
    ("searchLibrary(text)", "/api/library/search?query=credit+pull"),
    ("searchLibrary(phrase)", f"/api/library/search?mode=phrase&query={PHRASE.replace(' ', '+')}"),
    ("listPartners", "/api/partners"),
    ("getPartner", "/api/partners/{partner}"),
    ("listPartnerAttachments", "/api/partners/{partner}/attachments"),
    ("listOfferTerms", "/api/terms"),
    ("getCurrentOfferTerms", "/api/terms/current"),
    ("listNotifications", "/api/notifications"),
    ("listOutboxEmails", "/api/outbox"),
]


def _queries(client: Client, url: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, (url, response.content)
    return len(ctx.captured_queries)


@pytest.mark.django_db
@pytest.mark.parametrize(("operation", "path"), READS, ids=[op for op, _ in READS])
def test_read_endpoint_query_count_does_not_grow_with_rows(world: World, operation: str, path: str) -> None:
    del operation
    client = Client()
    client.force_login(world.lead)
    url = path.format(item=world.target.pk, partner=world.partner.pk)

    world.grow(1)
    small = _queries(client, url)
    world.grow(4)
    large = _queries(client, url)

    assert large == small
