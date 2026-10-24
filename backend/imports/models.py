"""Tracker imports: one job per uploaded workbook, one row record per sheet row once committed.

Persistence only: state changes go through `imports.services`.
"""

from django.conf import settings
from django.db import models

from imports.domain import ImportStatus


class ImportJob(models.Model):
    """An uploaded tracker on its way to legacy items: upload -> map -> preview -> commit (a Celery job).

    `workbook` is the parsed sheet (`imports.workbook.RawWorkbook` as JSON), read once at upload so preview and
    commit never re-open the xlsx. The mappings are what the admin confirmed (or the guesses, until they do).
    """

    status = models.CharField(max_length=20, default=ImportStatus.UPLOADED.value)
    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to="imports/%Y/%m/", max_length=500)
    sheet_name = models.CharField(max_length=100)
    workbook = models.JSONField()
    column_mapping = models.JSONField(default=dict)  # {header: ImportTargetField}
    status_mapping = models.JSONField(default=list)  # [{source_value, status, outcome}]
    value_mapping = models.JSONField(default=list)  # [{field, source_value, value}]
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    skip_blocked_rows = models.BooleanField(default=True)
    commit_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    commit_requested_at = models.DateTimeField(null=True, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)
    created_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    partners_created_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["-created_at"], name="import_job_created_idx")]

    def __str__(self) -> str:
        return f"Import {self.pk} {self.filename}"


class ImportRow(models.Model):
    """What commit did with one sheet row, and what it parsed: the durable record of tracker values that have
    no column on `ReviewItem` (trigger terms, approver, version #, placement)."""

    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    legacy_ref = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001  # null = not a data row
    action = models.CharField(max_length=30)
    item = models.ForeignKey("reviews.ReviewItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    problems = models.JSONField(default=list)
    parsed = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["job", "row_number"], name="import_row_unique_per_job")]

    def __str__(self) -> str:
        return f"Import {self.job_id} r{self.row_number}"
