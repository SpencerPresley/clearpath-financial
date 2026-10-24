from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, transaction

from core.db import constraint_name
from core.domain import PartnerStatus, PartnerType
from partners.models import Partner

AT = datetime(2026, 10, 1, tzinfo=UTC)


def _partner(name: str) -> Partner:
    return Partner.objects.create(name=name, type=PartnerType.AFFILIATE, created_at=AT, updated_at=AT)


@pytest.mark.django_db
def test_partner_defaults_to_active() -> None:
    assert _partner("LoanFinder").status == PartnerStatus.ACTIVE


@pytest.mark.django_db
def test_partner_name_unique_case_insensitive() -> None:
    _partner("LoanFinder")

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        _partner("loanfinder")

    assert constraint_name(caught.value) == "partner_name_ci_unique"
