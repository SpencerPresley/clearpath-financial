import pytest
from django.core.management import CommandError, call_command
from pydantic import SecretStr

from accounts.models import User
from core.domain import Role

PASSWORD = "demo-password-for-tests"  # noqa: S105  # test-only credential


@pytest.fixture
def demo_password(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("accounts.management.commands.seed_demo_users.env.demo_user_password", SecretStr(PASSWORD))
    return PASSWORD


@pytest.mark.django_db
def test_seed_creates_one_user_per_role(demo_password: str) -> None:
    call_command("seed_demo_users")

    users = {u.email: u for u in User.objects.all()}
    assert set(users) == {f"{r.value}@clearpath.demo" for r in Role}
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

    assert User.objects.count() == len(Role)
    reviewer.refresh_from_db()
    assert reviewer.check_password(demo_password)


@pytest.mark.django_db
def test_seed_rejects_a_weak_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("accounts.management.commands.seed_demo_users.env.demo_user_password", SecretStr("short"))

    with pytest.raises(CommandError, match="too weak"):
        call_command("seed_demo_users")


@pytest.mark.django_db
def test_seed_requires_a_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("accounts.management.commands.seed_demo_users.env.demo_user_password", None)

    with pytest.raises(CommandError, match="DEMO_USER_PASSWORD"):
        call_command("seed_demo_users")

    assert not User.objects.exists()
