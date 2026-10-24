from allauth.account.decorators import secure_admin_login
from django.contrib import admin
from django.urls import include, path

from config.api import api

# The admin's own password form would bypass allauth's rate limits and MFA (issue #18). Unauthenticated visitors
# are sent to settings.LOGIN_URL (the SPA's login) instead; signed-in non-staff get 403.
admin.site.login = secure_admin_login(admin.site.login)  # pyrefly: ignore[bad-assignment]

urlpatterns = [
    path("api/", api.urls),
    path("_allauth/", include("allauth.headless.urls")),
    path("accounts/", include("allauth.urls")),
    path("django-admin/", admin.site.urls),
]
