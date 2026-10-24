"""The lead's per-reviewer workload (spec §1, Compliance lead: workload balance). Its weighted load is
assignment's own (`reviews.assignment.weighted_loads`), so the panel shows the numbers auto-assignment ranks by."""

import pytest
from django.db import transaction
from django.test import Client

from accounts import selectors
from accounts.models import User
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import ItemStatus, RiskTier, Role
from core.errors import NotPermitted
from reviews.assignment import auto_assign
from reviews.tests.factories import make_item

pytestmark = pytest.mark.django_db


def _give(user: User, owner: User, *tiers: RiskTier, status: ItemStatus = ItemStatus.IN_REVIEW) -> None:
    for tier in tiers:
        make_item(owner, assignee=user, risk_tier=tier, status=status)


def test_workload_is_the_load_auto_assignment_ranks_by(
    user_factory: UserFactory, marketer: User, lead: User, clock: FixedClock
) -> None:
    dana = user_factory(roles=[Role.REVIEWER], display_name="Dana")
    sam = user_factory(roles=[Role.REVIEWER], display_name="Sam")
    _give(dana, marketer, RiskTier.HIGH, RiskTier.LOW)  # 3 + 1
    _give(dana, marketer, RiskTier.HIGH, status=ItemStatus.CHANGES_REQUESTED)  # with the marketer: not load
    _give(dana, marketer, RiskTier.HIGH, status=ItemStatus.APPROVED)
    _give(sam, marketer, RiskTier.MEDIUM, RiskTier.MEDIUM, RiskTier.HIGH)  # 2 + 2 + 3

    rows = {r.name: r for r in selectors.reviewer_workload(viewer=lead)}
    with transaction.atomic():
        assignment = auto_assign(item=make_item(marketer, status=ItemStatus.SUBMITTED), actor=None, clock=clock)

    assert assignment.reason == f"Dana: load {rows['Dana'].weighted_load} vs Sam {rows['Sam'].weighted_load}"
    assert (rows["Dana"].open_items, rows["Dana"].weighted_load) == (2, 4)
    assert (rows["Sam"].open_items, rows["Sam"].weighted_load) == (3, 7)


def test_workload_lists_reviewers_with_availability_and_whether_they_are_auto_assigned(
    user_factory: UserFactory, marketer: User, lead: User
) -> None:
    out = user_factory(roles=[Role.REVIEWER], display_name="Leah", is_available=False)
    idle = user_factory(roles=[Role.REVIEWER], display_name="Nikhil")
    user_factory(roles=[Role.MARKETER], display_name="Priya")
    _give(lead, marketer, RiskTier.MEDIUM)  # a lead who claimed an item: shown, but auto-assignment skips leads
    gone = user_factory(roles=[Role.REVIEWER], display_name="Gone")
    gone.is_active = False
    gone.save()

    rows = {r.name: r for r in selectors.reviewer_workload(viewer=lead)}

    assert set(rows) == {"Leah", "Nikhil", lead.display_name}
    assert (rows["Leah"].is_available, rows["Leah"].auto_assigned) == (False, False)
    assert (rows["Nikhil"].open_items, rows["Nikhil"].weighted_load, rows["Nikhil"].auto_assigned) == (0, 0, True)
    assert (rows[lead.display_name].weighted_load, rows[lead.display_name].auto_assigned) == (2, False)
    assert rows["Leah"].user_id == out.pk
    assert rows["Nikhil"].user_id == idle.pk


def test_workload_is_heaviest_first(user_factory: UserFactory, marketer: User, lead: User) -> None:
    light = user_factory(roles=[Role.REVIEWER], display_name="Ann")
    heavy = user_factory(roles=[Role.REVIEWER], display_name="Zed")
    _give(light, marketer, RiskTier.LOW)
    _give(heavy, marketer, RiskTier.HIGH)

    assert [r.user_id for r in selectors.reviewer_workload(viewer=lead)] == [heavy.pk, light.pk]


@pytest.mark.parametrize("role", [Role.MARKETER, Role.REVIEWER])
def test_workload_is_for_leads_and_admins(user_factory: UserFactory, role: Role) -> None:
    with pytest.raises(NotPermitted):
        selectors.reviewer_workload(viewer=user_factory(roles=[role]))


def test_workload_api(lead: User, admin_user: User, reviewer: User) -> None:
    client = Client()
    client.force_login(admin_user)

    response = client.get("/api/users/workload")

    assert response.status_code == 200, response.content
    assert response.json() == [
        {
            "user_id": reviewer.pk,
            "name": reviewer.display_name,
            "is_available": True,
            "auto_assigned": True,
            "open_items": 0,
            "weighted_load": 0,
        }
    ]
    del lead
