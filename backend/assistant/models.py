import uuid

from django.conf import settings
from django.db import models


class AssistantThread(models.Model):
    """One assistant conversation. The messages live only in the LangGraph checkpointer (keyed by `id`); this row
    carries ownership, the list view's fields, and the run lock."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    # Set while a request is running the agent on this thread; a second run is refused until it clears or goes stale.
    running_since = models.DateTimeField(null=True, blank=True)
    # Who holds that lock: the claim's token. Renewals move running_since (a lease), so release is keyed on this.
    run_token = models.UUIDField(null=True, blank=True)
    # True when the last run ended paused on an email approval.
    awaiting_approval = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["owner", "-updated_at"], name="assistant_thread_owner_idx")]

    def __str__(self) -> str:
        return self.title or str(self.id)
