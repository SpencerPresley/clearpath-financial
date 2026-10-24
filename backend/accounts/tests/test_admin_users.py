"""Admin user management (spec §1, Admin: Users): create, change roles, deactivate, with an event each, and the
last-admin guard. Enforced in services (spec §4.3), so the API tests only check the wiring."""

import threading

import pytest
from django.db import connection, transaction
from django.test import Client

from accounts import selectors, services
from accounts.models import User
from audit.models import Event
from conftest import TEST_PASSWORD, UserFactory
from core.clock import FixedClock
from core.domain import EventType, Role
from core.errors import Conflict, InvalidInput, NotFound, NotPermitted

pytestmark = pytest.mark.django_db

STRONG = "plum-lantern-orbit-42"


def _events(type_: EventType) -> list[dict[str, object]]:
    return [e.payload for e in Event.objects.filter(type=type_.value).order_by("id")]


# --- create ----------------------------------------------------------------------------------------------------


def test_admin_creates_a_user_who_can_sign_in(admin_user: User, clock: FixedClock) -> None:
    user_id = services.create_user(
        actor=admin_user,
        new=services.NewUser(
            email="Jo.Park@ClearPath.demo", display_name="Jo Park", roles=(Role.REVIEWER,), password=STRONG
        ),
        clock=clock,
    )

    user = User.objects.get(pk=user_id)
    assert (user.email, user.display_name, user.roles, user.is_active) == (
        "jo.park@clearpath.demo",
        "Jo Park",
        ["reviewer"],
        True,
    )
    assert user.check_password(STRONG)
    event = Event.objects.get(type=EventType.USER_CREATED.value)
    assert (event.actor, event.entity_id, event.at) == (admin_user, user_id, clock.now())
    assert event.payload == {"user_id": user_id, "email": "jo.park@clearpath.demo", "roles": ["reviewer"]}


def test_an_email_already_in_use_is_a_field_error(admin_user: User, user_factory: UserFactory) -> None:
    user_factory(email="taken@clearpath.demo")
    new = services.NewUser(email="TAKEN@clearpath.demo", display_name="Dup", roles=(Role.MARKETER,), password=STRONG)

    with pytest.raises(InvalidInput) as exc:
        services.create_user(actor=admin_user, new=new)

    assert exc.value.fields[0].loc == ("body", "email")


def test_a_weak_password_is_a_field_error(admin_user: User) -> None:
    new = services.NewUser(email="new@clearpath.demo", display_name="New", roles=(Role.MARKETER,), password="1" * 12)

    with pytest.raises(InvalidInput) as exc:
        services.create_user(actor=admin_user, new=new)

    assert exc.value.fields[0].loc == ("body", "password")
    assert not User.objects.filter(email="new@clearpath.demo").exists()


@pytest.mark.parametrize("role", [Role.MARKETER, Role.REVIEWER, Role.LEAD])
def test_only_admins_manage_users(user_factory: UserFactory, role: Role) -> None:
    actor = user_factory(roles=[role])
    target = user_factory(roles=[Role.MARKETER])
    new = services.NewUser(email="x@clearpath.demo", display_name="X", roles=(Role.MARKETER,), password=STRONG)

    with pytest.raises(NotPermitted):
        services.create_user(actor=actor, new=new)
    with pytest.raises(NotPermitted):
        services.update_user(actor=actor, user_id=target.pk, changes=services.UserChanges(is_active=False))


# --- update ----------------------------------------------------------------------------------------------------


def test_changing_roles_records_before_and_after(
    admin_user: User, user_factory: UserFactory, clock: FixedClock
) -> None:
    user = user_factory(roles=[Role.REVIEWER])

    services.update_user(
        actor=admin_user,
        user_id=user.pk,
        changes=services.UserChanges(roles=(Role.LEAD, Role.REVIEWER, Role.LEAD)),
        clock=clock,
    )

    user.refresh_from_db()
    assert user.roles == ["reviewer", "lead"]
    assert _events(EventType.USER_ROLES_CHANGED) == [
        {"user_id": user.pk, "before": ["reviewer"], "after": ["reviewer", "lead"]}
    ]


def test_deactivating_and_reactivating_record_an_event_each(
    admin_user: User, user_factory: UserFactory, clock: FixedClock
) -> None:
    user = user_factory(roles=[Role.REVIEWER])

    services.update_user(actor=admin_user, user_id=user.pk, changes=services.UserChanges(is_active=False), clock=clock)
    services.update_user(actor=admin_user, user_id=user.pk, changes=services.UserChanges(is_active=False), clock=clock)
    services.update_user(actor=admin_user, user_id=user.pk, changes=services.UserChanges(is_active=True), clock=clock)

    assert _events(EventType.USER_ACTIVE_CHANGED) == [
        {"user_id": user.pk, "is_active": False},
        {"user_id": user.pk, "is_active": True},
    ]


def test_a_deactivated_user_is_signed_out(admin_user: User, user_factory: UserFactory) -> None:
    user = user_factory(roles=[Role.REVIEWER])
    client = Client()
    client.force_login(user)
    assert client.get("/api/me").status_code == 200

    services.update_user(actor=admin_user, user_id=user.pk, changes=services.UserChanges(is_active=False))

    assert client.get("/api/me").status_code == 401
    assert not Client().login(email=user.email, password=TEST_PASSWORD)


def test_an_admin_marks_a_reviewer_out_of_office(admin_user: User, user_factory: UserFactory) -> None:
    user = user_factory(roles=[Role.REVIEWER])

    services.update_user(actor=admin_user, user_id=user.pk, changes=services.UserChanges(is_available=False))

    user.refresh_from_db()
    assert user.is_available is False
    event = Event.objects.get(type=EventType.USER_AVAILABILITY_CHANGED.value)
    assert (event.actor, event.payload) == (admin_user, {"user_id": user.pk, "is_available": False})


def test_an_unchanged_update_records_nothing(admin_user: User, user_factory: UserFactory) -> None:
    user = user_factory(roles=[Role.REVIEWER])

    services.update_user(
        actor=admin_user,
        user_id=user.pk,
        changes=services.UserChanges(roles=(Role.REVIEWER,), is_active=True, is_available=True),
    )

    assert not Event.objects.exists()


def test_an_unknown_user_is_404(admin_user: User) -> None:
    with pytest.raises(NotFound):
        services.update_user(actor=admin_user, user_id=999_999, changes=services.UserChanges(is_active=False))


# --- the last admin --------------------------------------------------------------------------------------------


def test_an_admin_can_not_deactivate_themselves(admin_user: User, user_factory: UserFactory) -> None:
    user_factory(roles=[Role.ADMIN])  # not the last admin either way

    with pytest.raises(Conflict, match="your own account"):
        services.update_user(actor=admin_user, user_id=admin_user.pk, changes=services.UserChanges(is_active=False))


def test_the_last_admin_keeps_the_admin_role(admin_user: User) -> None:
    with pytest.raises(Conflict, match="only admin"):
        services.update_user(
            actor=admin_user, user_id=admin_user.pk, changes=services.UserChanges(roles=(Role.REVIEWER,))
        )

    admin_user.refresh_from_db()
    assert admin_user.roles == ["admin"]
    assert not Event.objects.exists()


def test_an_admin_can_hand_the_role_on_once_someone_else_has_it(admin_user: User, user_factory: UserFactory) -> None:
    other = user_factory(roles=[Role.LEAD])
    services.update_user(
        actor=admin_user, user_id=other.pk, changes=services.UserChanges(roles=(Role.LEAD, Role.ADMIN))
    )

    services.update_user(actor=admin_user, user_id=admin_user.pk, changes=services.UserChanges(roles=(Role.LEAD,)))

    admin_user.refresh_from_db()
    assert admin_user.roles == ["lead"]


def test_an_inactive_admin_does_not_count(admin_user: User, user_factory: UserFactory) -> None:
    other = user_factory(roles=[Role.ADMIN])
    services.update_user(actor=admin_user, user_id=other.pk, changes=services.UserChanges(is_active=False))

    with pytest.raises(Conflict, match="only admin"):
        services.update_user(actor=admin_user, user_id=admin_user.pk, changes=services.UserChanges(roles=(Role.LEAD,)))


@pytest.mark.django_db(transaction=True)
def test_two_admins_demoting_each_other_at_once_leave_one_admin(user_factory: UserFactory) -> None:
    """Both read "2 admins" without the lock and both succeed, leaving none. With it, the second waits for the
    first and then sees one admin left."""
    a = user_factory(roles=[Role.ADMIN])
    b = user_factory(roles=[Role.ADMIN])
    first_inside = threading.Event()
    results: dict[str, str] = {}

    def demote(actor: User, target: User, key: str, hold: bool) -> None:
        try:
            with transaction.atomic():
                services.update_user(actor=actor, user_id=target.pk, changes=services.UserChanges(roles=(Role.LEAD,)))
                if hold:
                    first_inside.set()
                    threading.Event().wait(0.3)
            results[key] = "ok"
        except Conflict:
            results[key] = "conflict"
        finally:
            connection.close()

    t1 = threading.Thread(target=demote, args=(a, b, "a", True))
    t1.start()
    first_inside.wait(5)
    t2 = threading.Thread(target=demote, args=(b, a, "b", False))
    t2.start()
    t1.join(10)
    t2.join(10)

    assert sorted(results.values()) == ["conflict", "ok"]
    assert User.objects.filter(roles__contains=[Role.ADMIN.value], is_active=True).count() == 1


# --- API -------------------------------------------------------------------------------------------------------


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def test_api_create_then_update(admin_user: User) -> None:
    client = _client(admin_user)

    created = client.post(
        "/api/admin/users",
        {"email": "new@clearpath.demo", "display_name": "New Person", "roles": ["marketer"], "password": STRONG},
        content_type="application/json",
    )
    assert created.status_code == 201, created.content
    user_id = created.json()["id"]
    assert created.json() == {
        "id": user_id,
        "email": "new@clearpath.demo",
        "display_name": "New Person",
        "roles": ["marketer"],
        "is_available": True,
        "is_active": True,
    }

    updated = client.patch(
        f"/api/admin/users/{user_id}", {"roles": ["reviewer"], "is_active": False}, content_type="application/json"
    )
    assert updated.status_code == 200, updated.content
    assert (updated.json()["roles"], updated.json()["is_active"]) == (["reviewer"], False)


def test_api_last_admin_is_409_and_non_admin_403(admin_user: User, lead: User) -> None:
    refused = _client(admin_user).patch(
        f"/api/admin/users/{admin_user.pk}", {"roles": ["lead"]}, content_type="application/json"
    )
    forbidden = _client(lead).patch(
        f"/api/admin/users/{admin_user.pk}", {"is_active": False}, content_type="application/json"
    )

    assert (refused.status_code, refused.json()["code"]) == (409, "conflict")
    assert forbidden.status_code == 403


def test_get_user_returns_the_row(admin_user: User) -> None:
    assert selectors.get_user(admin_user.pk).email == admin_user.email
