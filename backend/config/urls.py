from django.contrib import admin
from django.urls import include, path

from config.api import api

urlpatterns = [
    path("api/", api.urls),
    path("_allauth/", include("allauth.headless.urls")),
    path("accounts/", include("allauth.urls")),
    path("django-admin/", admin.site.urls),
]
