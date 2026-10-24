from typing import ClassVar

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from accounts.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """A ClearPath staff member. Email is the login; roles are a list so new roles are additive."""

    email = models.EmailField(max_length=254, unique=True)
    display_name = models.CharField(max_length=120, blank=True)
    roles = ArrayField(models.CharField(max_length=20), default=list, blank=True)
    # Out-of-office reviewers are skipped by auto-assignment (decisions.md "Reviewer assignment").
    is_available = models.BooleanField(default=True)
    # Assignment tie-break: whoever has gone longest without a new assignment.
    last_assigned_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects = UserManager()

    class Meta:
        constraints = [
            # Stored lower-cased, so the unique index is case-insensitive.
            models.CheckConstraint(condition=models.Q(email=Lower("email")), name="user_email_lowercase"),
        ]

    def __str__(self) -> str:
        return self.display_name or self.email

    def get_full_name(self) -> str:
        return self.display_name or self.email

    def get_short_name(self) -> str:
        return self.display_name or self.email
