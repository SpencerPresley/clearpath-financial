import pytest
from django.core.management import CommandError, call_command
from pydantic import SecretStr

from accounts.models import User
from core.domain import Role
from demo.content.people import PERSONAS
from demo.users import DOCUMENTED_PASSWORD

PASSWORD = "demo-password-for-tests"  # noqa: S105  # test-only credential


@pytest.fixture
def demo_password(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("demo.users.env.demo_user_password", SecretStr(PASSWORD))
    return PASSWORD


@pytest.mark.django_db
def test_seed_creates_one_login_per_role_and_the_team(demo_password: str) -> None:
    call_command("seed_demo_users")

    users = {u.email: u for u in User.objects.all()}
    assert set(users) == {p.email for p in PERSONAS}
    for role in Role:
        user = users[f"{role.value}@clearpath.demo"]
        assert user.roles == [role.value]
        assert user.check_password(demo_password)
        assert user.display_name
    assert not any(u.is_staff or u.is_superuser for u in users.values())


@pytest.mark.django_db
def test_seed_is_idempotent_and_resets_passwords(demo_password: str) -> None:
    call_command("seed_demo_users")
    reviewer = User.objects.get(email="reviewer@clearpath.demo")
    reviewer.set_password("changed-by-someone")
    reviewer.save()

    call_command("seed_demo_users")

    assert User.objects.count() == len(PERSONAS)
    reviewer.refresh_from_db()
    assert reviewer.check_password(demo_password)


@pytest.mark.django_db
def test_seed_rejects_a_weak_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("demo.users.env.demo_user_password", SecretStr("short"))

    with pytest.raises(CommandError, match="too weak"):
        call_command("seed_demo_users")

    assert not User.objects.exists()


@pytest.mark.django_db
def test_without_a_password_the_documented_one_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("demo.users.env.demo_user_password", None)

    call_command("seed_demo_users")

    assert User.objects.get(email="lead@clearpath.demo").check_password(DOCUMENTED_PASSWORD)
