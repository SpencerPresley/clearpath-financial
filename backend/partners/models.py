from django.db import models
from django.db.models.functions import Lower

from core.db import enum_choices
from core.domain import PartnerStatus, PartnerType


class Partner(models.Model):
    """An affiliate, lead-gen site, or marketplace that publishes content on ClearPath's behalf."""

    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=enum_choices(PartnerType))
    status = models.CharField(max_length=20, choices=enum_choices(PartnerStatus), default=PartnerStatus.ACTIVE.value)
    website = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True)
    agreement_signed_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(Lower("name"), name="partner_name_ci_unique")]

    def __str__(self) -> str:
        return self.name
