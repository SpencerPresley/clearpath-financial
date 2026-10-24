from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        # Registers the production configuration check (`manage.py check --deploy`).
        from core import deploy_checks  # noqa: F401, PLC0415
