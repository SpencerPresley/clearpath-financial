"""Row factories for tests that need persisted items without going through services."""

from datetime import UTC, date, datetime
from typing import Any

from accounts.models import User
from core.domain import Channel, ItemStatus, Market, PartnerType, Product, RiskTier, VersionOrigin
from partners.models import Partner
from reviews.models import ReviewItem, Version

AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def make_partner(name: str = "LoanFinder") -> Partner:
    return Partner.objects.create(name=name, type=PartnerType.AFFILIATE, created_at=AT, updated_at=AT)


def make_item(owner: User | None, **overrides: Any) -> ReviewItem:
    fields: dict[str, Any] = {
        "title": "Spring personal loan email",
        "product": Product.PERSONAL_LOAN,
        "channel": Channel.EMAIL,
        "markets": [Market.NATIONAL],
        "owner": owner,
        "status": ItemStatus.SUBMITTED,
        "risk_tier": RiskTier.LOW,
        "planned_first_run": date(2026, 11, 1),
        "submitted_at": AT,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    fields.setdefault("queue_entered_at", fields["submitted_at"])
    return ReviewItem.objects.create(**fields)


def make_version(item: ReviewItem, text: str = "Rates from 7.49% APR.", n: int = 1, **overrides: Any) -> Version:
    fields: dict[str, Any] = {
        "item": item,
        "n": n,
        "content_text": text,
        "content_sha256": Version.hash_content(text),
        "author": item.owner or overrides["author"],
        "origin": VersionOrigin.SUBMISSION,
        "created_at": AT,
    }
    fields.update(overrides)
    version = Version.objects.create(**fields)
    if item.current_version_id is None or n > 1:
        ReviewItem.objects.filter(pk=item.pk).update(current_version=version)
        item.current_version = version
    return version
