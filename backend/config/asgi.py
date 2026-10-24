import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()

# After setup, before serving: a production worker without its AI key or documents bucket raises here instead of
# serving AI-less approvals (core/deploy_checks.py). A no-op outside production.
from core.deploy_checks import require_production_config  # noqa: E402

require_production_config()
