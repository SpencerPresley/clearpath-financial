"""Public demo partner pages, mounted at /demo-partners/ by config/urls.py."""

from django.urls import path

from drift import views

app_name = "demo_partners"
urlpatterns = [path("<slug:slug>/", views.partner_page, name="page")]
