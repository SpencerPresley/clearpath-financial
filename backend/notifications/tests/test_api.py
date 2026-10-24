import pytest
from django.test import Client

from accounts.models import User
from core.domain import NotificationKind
from notifications.models import Notification, OutboxEmail
from reviews.tests.factories import AT, make_item


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_notifications_list_and_mark_read(marketer: User, reviewer: User) -> None:
    item = make_item(marketer)
    mine = [
        Notification.objects.create(
            user=reviewer, kind=NotificationKind.ASSIGNMENT, item=item, message=f"n{i}", created_at=AT
        )
        for i in range(2)
    ]
    Notification.objects.create(user=marketer, kind=NotificationKind.DECISION, message="not mine", created_at=AT)
    client = _client(reviewer)

    page = client.get("/api/notifications").json()
    assert page["unread_count"] == 2
    assert {r["item_key"] for r in page["rows"]} == {item.key}

    assert client.post(f"/api/notifications/{mine[0].pk}/read").status_code == 204
    assert client.get("/api/notifications?unread_only=true").json()["unread_count"] == 1
    assert client.post("/api/notifications/read-all").json() == {"marked": 1}


@pytest.mark.django_db
def test_cannot_mark_someone_elses_notification(marketer: User, reviewer: User) -> None:
    theirs = Notification.objects.create(user=marketer, kind=NotificationKind.DECISION, message="x", created_at=AT)

    assert _client(reviewer).post(f"/api/notifications/{theirs.pk}/read").status_code == 404


@pytest.mark.django_db
def test_outbox_lists_sent_emails(reviewer: User, lead: User) -> None:
    email = OutboxEmail.objects.create(
        to=["dana@clearpath.demo"],
        subject="Queue summary",
        body="3 items waiting",
        html_body="<p>3 items waiting</p>",
        requested_by=reviewer,
        approved_by=reviewer,
        sent_at=AT,
    )
    client = _client(lead)

    assert [e["subject"] for e in client.get("/api/outbox").json()] == ["Queue summary"]
    detail = client.get(f"/api/outbox/{email.pk}").json()
    assert detail["to"] == ["dana@clearpath.demo"]
    assert detail["html_body"] == "<p>3 items waiting</p>"
