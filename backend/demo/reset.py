"""Wipe the domain data and seed the demo, in one transaction.

- **All or nothing.** TRUNCATE and the whole seed share one transaction under an advisory lock, so a failure (a weak
  password, a story the services refuse) leaves the previous demo exactly as it was, and two resets run one after
  the other. TRUNCATE is allowed by the insert-only triggers on purpose (`core.db.forbid_mutation`); RESTART
  IDENTITY makes item keys (CP-1, CP-2, ...) the same after every reset.
- **People survive.** Users and sessions aren't truncated: the admin who pressed Reset stays signed in, and the
  personas are upserted (password, roles, availability) instead of recreated.
- **Nothing leaks to the worker.** While the seed's transaction is open, the beat dispatcher can't see its events
  (they're uncommitted) and the runner delivers them in-process, writing their receipts. The handlers that would
  enqueue Celery work on commit (the AI check, the terms fan-out, the import commit, the drift check) are pointed
  at no-ops for the duration, including the commit, so no seeded version gets a live AI call. The one item left
  with a pending AI check is picked up by the reconciler once it's older than its STUCK_AFTER (10 minutes).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from django.apps import apps
from django.db import connection, transaction

from accounts.models import User
from audit.outbox import dispatch_pending
from audit.payloads import DemoResetPayload
from audit.services import record_event
from checks import handlers as check_handlers
from checks import prereview
from core.clock import SYSTEM_CLOCK, FixedClock
from core.domain import EntityType, EventType
from demo.content import CATALOG
from demo.runner import run_catalog
from demo.story import Catalog
from demo.users import check_password_strength, demo_password, upsert_personas
from drift import services as drift_services
from drift.demo import reset_demo_pages
from imports import services as import_services
from notifications.models import Notification
from notifications.services import mark_read
from reviews.models import ReviewItem
from terms import handlers as terms_handlers

# "DEMO" as a big-endian int: serializes resets (and seeds) across processes.
RESET_LOCK_KEY: Final = 0x4445_4D4F
# Apps whose tables a reset keeps: people, sessions, framework tables, and the reset's own record.
KEPT_APPS: Final = frozenset(
    {
        "admin",
        "auth",
        "contenttypes",
        "sessions",
        "account",
        "headless",
        "mfa",
        "socialaccount",
        "accounts",
        "core",
        "demo",
    }
)
# Configuration rows seeded by migrations, not demo data.
KEPT_TABLES: Final = frozenset({"reviews_expirypolicy"})
# Notifications older than this are marked read: a reviewer coming back to the demo sees this week's, not ten weeks'.
UNREAD_WINDOW: Final = timedelta(days=2)


@dataclass(frozen=True)
class SeedResult:
    items: int
    legacy_items: int
    users: int


def domain_tables() -> tuple[str, ...]:
    """Every table a reset empties: all models (and their M2M tables) outside KEPT_APPS, minus KEPT_TABLES."""
    metas = [model._meta for model in apps.get_models(include_auto_created=True)]  # noqa: SLF001  # Django's API
    tables = {m.db_table for m in metas if m.app_label not in KEPT_APPS and m.managed and not m.proxy}
    return tuple(sorted(tables - KEPT_TABLES))


def has_demo_data() -> bool:
    return ReviewItem.objects.exists()


def _noop(*_args: object) -> None:
    return None


@contextmanager
def quiet_side_effects() -> Iterator[None]:
    """Point the on-commit task seams at no-ops (see the module docstring) and restore them afterwards."""
    saved = (
        prereview.enqueue,
        terms_handlers.enqueue_fan_out,
        import_services._enqueue_commit,  # noqa: SLF001
        drift_services.enqueue,
        check_handlers.clock,
    )
    prereview.enqueue = _noop
    terms_handlers.enqueue_fan_out = _noop
    import_services._enqueue_commit = _noop  # noqa: SLF001
    drift_services.enqueue = _noop
    try:
        yield
    finally:
        (
            prereview.enqueue,
            terms_handlers.enqueue_fan_out,
            import_services._enqueue_commit,  # noqa: SLF001
            drift_services.enqueue,
            check_handlers.clock,
        ) = saved


def _truncate() -> None:
    names = ", ".join(connection.ops.quote_name(t) for t in domain_tables())
    with connection.cursor() as cursor:
        cursor.execute(f"TRUNCATE {names} RESTART IDENTITY")  # table names from the app registry


def _mark_old_notifications_read(now: datetime) -> None:
    old = Notification.objects.filter(read_at__isnull=True, created_at__lt=now - UNREAD_WINDOW).select_related("user")
    for notification in old.order_by("pk"):
        read_at = FixedClock(notification.created_at + timedelta(hours=3))
        mark_read(user=notification.user, notification_id=notification.pk, clock=read_at)


def reset_demo(
    *,
    requested_by: User | None = None,
    now: datetime | None = None,
    password: str | None = None,
    catalog: Catalog = CATALOG,
) -> SeedResult:
    """Empty the domain tables and replay the catalog, ending at `now` (default: the current time)."""
    password = password or demo_password()
    check_password_strength(password)
    at = now or SYSTEM_CLOCK.now()
    with quiet_side_effects(), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [RESET_LOCK_KEY])
        _truncate()
        users = upsert_personas(catalog.personas, password=password)
        run = run_catalog(catalog=catalog, now=at, users=users)
        # The demo partner pages' state is in the cache, not the database. Set inside the transaction so a cache
        # that can't be reached fails the whole reset instead of leaving the pages and the drift history disagreeing.
        reset_demo_pages(edited=run.edited_pages)
        _mark_old_notifications_read(at)
        items = ReviewItem.objects.filter(is_legacy=False).count()
        record_event(
            type=EventType.DEMO_RESET,
            entity=EntityType.SYSTEM,
            entity_id=0,
            payload=DemoResetPayload(seeded_items=items),
            actor=requested_by,
            at=at,
        )
        dispatch_pending(enqueue=_noop)  # no handler listens to DEMO_RESET; this moves the cursor past it
        return SeedResult(
            items=items,
            legacy_items=ReviewItem.objects.filter(is_legacy=True).count(),
            users=len(run.users),
        )
