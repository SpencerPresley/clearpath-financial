from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"

    def ready(self) -> None:
        # Each app registers its outbox handlers in handlers.py (see audit.outbox).
        autodiscover_modules("handlers")
