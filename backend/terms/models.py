from typing import Any, Final

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models.fields.json import KT
from pydantic import TypeAdapter

from core.domain import CreditCardTerms, OfferTermsValues, PersonalLoanTerms

TERMS_VALUES: Final[TypeAdapter[PersonalLoanTerms | CreditCardTerms]] = TypeAdapter(OfferTermsValues)


class OfferTerms(models.Model):
    """One version of a product's current rates and fees (spec §4.2 ruling 1).

    `effective_range` is half-open `[from, to)`; the EXCLUDE constraint guarantees exactly one version is in
    effect per product at any instant. Publishing a new version closes the previous one's range at the same
    instant. `values` is JSONB validated through `core.domain.OfferTermsValues` on every save.
    """

    product = models.CharField(max_length=30)
    version = models.PositiveIntegerField()
    effective_range = DateTimeRangeField()
    values = models.JSONField()
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "version"], name="terms_version_unique_per_product"),
            ExclusionConstraint(
                name="terms_no_overlap",
                expressions=[("product", RangeOperators.EQUAL), ("effective_range", RangeOperators.OVERLAPS)],
            ),
            models.CheckConstraint(
                condition=models.Q(effective_range__isempty=False, effective_range__lower_inf=False),
                name="terms_range_bounded_below",
            ),
            models.CheckConstraint(
                condition=models.Q(product=KT("values__product")), name="terms_values_product_matches"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} v{self.version}"

    def save(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401  # Model.save's signature
        # Last line of defense for the JSONB shape; services validate first and pass typed values.
        self.values = TERMS_VALUES.dump_python(TERMS_VALUES.validate_python(self.values), mode="json")
        super().save(*args, **kwargs)

    @property
    def typed_values(self) -> PersonalLoanTerms | CreditCardTerms:
        return TERMS_VALUES.validate_python(self.values)
