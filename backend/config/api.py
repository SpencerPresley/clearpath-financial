from ninja import NinjaAPI
from ninja.security import django_auth

from core.api import router as core_router

# Session-cookie auth by default; django_auth enforces CSRF on unsafe methods.
# Public endpoints opt out per operation with auth=None.
api = NinjaAPI(
    title="ClearPath Compliance Review API",
    version="0.1.0",
    auth=django_auth,
    urls_namespace="api",
)

api.add_router("/", core_router)
