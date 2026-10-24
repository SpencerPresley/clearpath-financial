"""Findings, offer-terms references detected in copy, and check runs.

Rules live in code (workstream C, `checks/engine/`), not in a table: a Finding stores `rule_id`, `citation`, and
`severity` as snapshots of the rule at the time it fired, so a later rule change never rewrites history.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThan

from core.domain import CheckStatus, FindingSource, FindingState, Severity


def _span_valid() -> Q:
    return Q(span_start__isnull=True, span_end__isnull=True) | Q(span_start__gte=0, span_end__gt=F("span_start"))


class Finding(models.Model):
    """A flagged problem on one version. Code and AI findings point at `[span_start, span_end)`; human
    checklist items (`source=human`) have no span."""

    version = models.ForeignKey("reviews.Version", on_delete=models.PROTECT, related_name="findings")
    rule_id = models.CharField(max_length=100)
    citation = models.CharField(max_length=200)
    source = models.CharField(max_length=10)
    severity = models.CharField(max_length=10)
    state = models.CharField(max_length=10, default=FindingState.OPEN.value)
    span_start = models.PositiveIntegerField(null=True, blank=True)
    span_end = models.PositiveIntegerField(null=True, blank=True)
    quote = models.TextField(null=True, blank=True)  # noqa: DJ001  # null iff span is null
    message = models.TextField()
    suggested_fix = models.TextField(blank=True)
    reason = models.TextField(blank=True)  # why it was dismissed (or a note on acceptance)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Same rule + same quote as a finding already dismissed on an earlier version: the dismissal carries
    # forward, marked as carried (spec §4.2 ruling 4).
    carried_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=_span_valid(), name="finding_span_valid"),
            models.CheckConstraint(
                condition=Q(span_start__isnull=True, quote__isnull=True)
                | Q(span_start__isnull=False, quote__isnull=False),
                name="finding_quote_iff_span",
            ),
            models.CheckConstraint(
                condition=~Q(state=FindingState.DISMISSED.value) | Q(GreaterThan(Length(Trim("reason")), 0)),
                name="finding_dismissal_has_reason",
            ),
            # A resolution has a time and a person, except a dismissal by the system (evidence attached that
            # answers the finding, `checks.services.recheck_for_evidence`), which has no person.
            models.CheckConstraint(
                condition=Q(state=FindingState.OPEN.value)
                | Q(resolved_by__isnull=False, resolved_at__isnull=False)
                | Q(state=FindingState.DISMISSED.value, resolved_at__isnull=False),
                name="finding_resolution_recorded",
            ),
            models.CheckConstraint(
                condition=Q(carried_from__isnull=True) | Q(state=FindingState.DISMISSED.value),
                name="finding_carried_is_dismissed",
            ),
            # Orchestrator ruling: the AI never blocks on its own judgment; blocking stays with code and humans.
            models.CheckConstraint(
                condition=~Q(source=FindingSource.LLM.value) | Q(severity=Severity.WARNING.value),
                name="finding_llm_is_warning",
            ),
            models.UniqueConstraint(
                fields=["version", "source", "rule_id", "span_start", "span_end"],
                nulls_distinct=False,
                name="finding_unique_per_version_rule_span",
            ),
        ]
        indexes = [
            models.Index(fields=["version"], condition=Q(state=FindingState.OPEN.value), name="finding_open_idx"),
            models.Index(fields=["version", "rule_id"], name="finding_version_rule_idx"),
            models.Index(fields=["rule_id", "-created_at"], name="finding_rule_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.rule_id} finding {self.pk}"


class TermsRef(models.Model):
    """A rate, fee, or representative-example claim found in a version's copy (spec §4.2 ruling 1).

    An approved item "quotes v12" if its approved version (the version of its latest approving Decision) has
    TermsRefs to OfferTerms v12. Not the current version: after a terms change, fast-track generates v+1 and
    current moves on while the approval still covers the old text. Fast-track replaces these spans in v+1.
    """

    version = models.ForeignKey("reviews.Version", on_delete=models.PROTECT, related_name="terms_refs")
    offer_terms = models.ForeignKey("terms.OfferTerms", on_delete=models.PROTECT, related_name="terms_refs")
    field = models.CharField(max_length=40)
    span_start = models.PositiveIntegerField()
    span_end = models.PositiveIntegerField()
    quote = models.TextField()
    quoted_value = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(span_end__gt=F("span_start")), name="terms_ref_span_valid"),
            models.UniqueConstraint(
                fields=["version", "span_start", "span_end", "field"], name="terms_ref_unique_span"
            ),
        ]
        indexes = [models.Index(fields=["offer_terms", "version"], name="terms_ref_terms_idx")]

    def __str__(self) -> str:
        return f"{self.field}={self.quoted_value}"


class CheckRun(models.Model):
    """One execution of the code or AI checks on a version. Checks don't re-run for identical text: the
    cache key is (content_sha256, source, ruleset_key) (spec §7 Cost)."""

    version = models.ForeignKey("reviews.Version", on_delete=models.PROTECT, related_name="check_runs")
    source = models.CharField(max_length=10)
    status = models.CharField(max_length=20, default=CheckStatus.PENDING.value)
    content_sha256 = models.CharField(max_length=64)
    ruleset_key = models.CharField(max_length=100)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    findings_count = models.PositiveIntegerField(default=0)
    # LLM findings whose quote didn't sit exactly at their span are dropped and counted, never stored.
    dropped_findings_count = models.PositiveIntegerField(default=0)
    model = models.CharField(max_length=100, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    # AI checks only (code runs leave these unset). The retry budget lives on the run, not in the task message,
    # so a re-enqueued run doesn't start a fresh budget: model calls started, unreadable answers, and when the
    # check was requested (never rewritten; `started_at` is the current attempt's start).
    attempts = models.PositiveSmallIntegerField(default=0)
    invalid_outputs = models.PositiveSmallIntegerField(default=0)
    requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["content_sha256", "source", "ruleset_key"], name="check_run_cache_idx"),
            models.Index(fields=["version", "-started_at"], name="check_run_version_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source} check {self.status}"
