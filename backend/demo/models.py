"""A Reset demo request and how it went. Outside the domain tables, so a reset doesn't wipe its own record."""

from django.conf import settings
from django.db import models


class DemoReset(models.Model):
    status = models.CharField(max_length=20)  # demo.services.ResetStatus
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    requested_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    seeded_items = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"demo reset {self.pk} ({self.status})"
