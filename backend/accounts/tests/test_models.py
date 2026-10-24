import pytest
from django.db import IntegrityError, connection, transaction

from accounts.models import User
from conftest import UserFactory
from core.domain import Role


def test_email_is_the_login_field() -> None:
    assert User.USERNAME_FIELD == "email"
    assert "username" not in {f.name for f in User._meta.get_fields()}


@pytest.mark.django_db
def test_email_is_normalized_and_case_insensitive_unique(user_factory: UserFactory) -> None:
    user = user_factory(email="Dana@ClearPath.Demo")

    assert user.email == "dana@clearpath.demo"
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(email="DANA@clearpath.demo", display_name="Dup")


@pytest.mark.django_db
def test_roles_check_rejects_unknown_role(user_factory: UserFactory) -> None:
    user = user_factory(roles=[Role.REVIEWER])

    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE accounts_user SET roles = ARRAY['partner'] WHERE id = %s", [user.pk])


@pytest.mark.django_db
def test_roles_round_trip_as_role_enums(user_factory: UserFactory) -> None:
    user = user_factory(roles=[Role.REVIEWER, Role.LEAD])
    user.refresh_from_db()

    assert set(user.roles) == {Role.REVIEWER, Role.LEAD}
    assert user.is_available is True
    assert user.last_assigned_at is None


@pytest.mark.django_db
def test_create_superuser_needs_no_username() -> None:
    admin = User.objects.create_superuser(email="root@clearpath.test", password="x" * 12)

    assert admin.is_staff
    assert admin.is_superuser
