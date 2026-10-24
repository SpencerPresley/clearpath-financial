"""Export jobs: an xlsx of a filtered view, or one item's evidence pack. Persistence only."""

from django.conf import settings
from django.db import models

from exports.domain import ExportKind, ExportStatus


class ExportJob(models.Model):
    """A file built in the background (CloudFront drops origin requests idle for 60 s) and downloaded through
    `downloadExport`, which checks who is asking. The stored file name is random; nothing is public."""

    kind = models.CharField(max_length=20, default=ExportKind.ITEMS_XLSX.value)
    status = models.CharField(max_length=20, default=ExportStatus.PENDING.value)
    filters = models.JSONField(default=dict)  # ItemFilter
    sort = models.CharField(max_length=20, default="newest")
    include_evidence_packs = models.BooleanField(default=False)
    item = models.ForeignKey("reviews.ReviewItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    file = models.FileField(upload_to="exports/%Y/%m/", max_length=500, blank=True)
    filename = models.CharField(max_length=255, blank=True)
    item_count = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(kind=ExportKind.EVIDENCE_PACK.value) | models.Q(item__isnull=False),
                name="export_evidence_pack_has_item",
            ),
        ]
        indexes = [models.Index(fields=["created_by", "-created_at"], name="export_job_owner_idx")]

    def __str__(self) -> str:
        return f"Export {self.pk} {self.kind}"
