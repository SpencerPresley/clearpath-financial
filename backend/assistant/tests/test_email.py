from typing import Any

import pytest

from accounts.models import User
from assistant.email import EmailDraft, allowed_recipients, check_recipients, send_approved_email
from audit.models import Event
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import EntityType, EventType, Role
from core.errors import InvalidInput
from notifications.models import OutboxEmail
from reviews.tests.factories import make_item


def _rejected(to: list[str]) -> InvalidInput:
    with pytest.raises(InvalidInput) as exc:
        check_recipients(to)
    return exc.value


@pytest.mark.django_db
def test_allowlist_is_active_users_and_team_aliases_at_the_domain(dana: User, user_factory: UserFactory) -> None:
    user_factory(email="someone@clearpath.test")  # active, but another domain

    assert allowed_recipients() == frozenset(
        {"dana@clearpath.demo", "compliance@clearpath.demo", "marketing@clearpath.demo", "legal@clearpath.demo"}
    )


@pytest.mark.django_db
def test_allowed_recipients_are_normalized_and_deduped(dana: User) -> None:
    assert check_recipients([" Dana@ClearPath.demo ", "dana@clearpath.demo", "legal@clearpath.demo"]) == (
        "dana@clearpath.demo",
        "legal@clearpath.demo",
    )


@pytest.mark.django_db
def test_outsider_is_rejected_on_the_to_field(dana: User) -> None:
    error = _rejected(["dana@clearpath.demo", "partner@evil.example"])

    assert error.message == "Not an internal address: partner@evil.example"
    assert [f.loc for f in error.fields] == [("body", "to")]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "address",
    [
        '"dana@clearpath.demo" <x@evil.com>',  # display name shows the internal address, mail goes outside
        "Dana <dana@clearpath.demo>",  # even a harmless display name: only bare addresses
        "dana@clearpath.demo.evil.com",  # look-alike domain
        "dana@evil.com@clearpath.demo",
        "dana@sub.clearpath.demo",
        "dana@clearpath.demo, x@evil.com",
        "",
    ],
)
def test_tricks_are_rejected(dana: User, address: str) -> None:
    _rejected([address])


@pytest.mark.django_db
def test_inactive_users_address_is_rejected(user_factory: UserFactory) -> None:
    gone = user_factory(email="gone@clearpath.demo")
    gone.is_active = False
    gone.save()

    assert "gone@clearpath.demo" not in allowed_recipients()
    _rejected(["gone@clearpath.demo"])


@pytest.mark.django_db
def test_no_recipients_is_rejected() -> None:
    assert _rejected([]).message == "Add at least one recipient."


@pytest.mark.django_db
def test_send_writes_one_outbox_email_and_one_event(owner: User, dana: User, clock: FixedClock) -> None:
    item = make_item(owner, title="Spring personal loan email")
    draft = EmailDraft(
        to=("Dana@clearpath.demo",),
        subject="CP findings",
        body="Two findings need a look.\n\n<script>alert(1)</script> & more",
        item_id=item.pk,
    )

    email_id = send_approved_email(requester=owner, approver=owner, draft=draft, thread_id="t-1", clock=clock).outbox_id

    email = OutboxEmail.objects.get()
    assert email.pk == email_id
    assert email.to == ["dana@clearpath.demo"]
    assert email.subject == "CP findings"
    assert email.item == item
    assert (email.requested_by, email.approved_by, email.thread_id, email.sent_at) == (owner, owner, "t-1", clock.now())
    assert "<script>alert(1)</script> & more" in email.body
    assert f"{item.key}" in email.body
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more" in email.html_body
    assert "<script>" not in email.html_body
    assert "<p>Two findings need a look.</p>" in email.html_body
    assert f"/items/{item.pk}" in email.html_body

    event = Event.objects.get(type=EventType.EMAIL_SENT)
    assert (event.entity, event.entity_id, event.item, event.actor) == (EntityType.EMAIL, email.pk, item, owner)
    assert event.payload == {
        "email_id": email.pk,
        "to": ["dana@clearpath.demo"],
        "subject": "CP findings",
        "approved_by_id": owner.pk,
    }


@pytest.mark.django_db
def test_send_rechecks_recipients(owner: User, clock: FixedClock) -> None:
    draft = EmailDraft(to=("partner@evil.example",), subject="s", body="b", item_id=None)

    with pytest.raises(InvalidInput):
        send_approved_email(requester=owner, approver=owner, draft=draft, thread_id="t", clock=clock)

    assert not OutboxEmail.objects.exists()
    assert not Event.objects.filter(type=EventType.EMAIL_SENT).exists()


@pytest.mark.django_db
def test_send_without_item(user_factory: UserFactory, dana: User, clock: FixedClock) -> None:
    lead = user_factory(roles=[Role.LEAD])
    draft = EmailDraft(to=("compliance@clearpath.demo",), subject="Queue", body="3 waiting", item_id=None)

    send_approved_email(requester=lead, approver=lead, draft=draft, thread_id="t", clock=clock)

    assert OutboxEmail.objects.get().item is None


@pytest.mark.django_db
def test_recipient_check_queries_only_the_candidates(
    dana: User,
    user_factory: UserFactory,
    django_assert_num_queries: Any,
) -> None:
    for i in range(20):
        user_factory(email=f"staff{i}@clearpath.demo")

    with django_assert_num_queries(1) as ctx:
        assert check_recipients(["dana@clearpath.demo", "legal@clearpath.demo"]) == (
            "dana@clearpath.demo",
            "legal@clearpath.demo",
        )

    assert "staff1" not in ctx.captured_queries[0]["sql"]
    assert "dana@clearpath.demo" in ctx.captured_queries[0]["sql"]
