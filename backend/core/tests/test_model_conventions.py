"""Conventions every app's models follow so workstreams can extend shared enums without migrating apps they
don't own (product-spec "Roles": a new role is an addition, not a migration)."""

from django.apps import apps
from django.contrib.postgres.fields import ArrayField

OUR_APPS = {"accounts", "partners", "terms", "reviews", "checks", "audit", "notifications"}


def test_model_fields_carry_no_enum_choices() -> None:
    offenders = []
    for model in apps.get_models():
        if model._meta.app_label not in OUR_APPS:
            continue
        for field in model._meta.get_fields():
            inner = field.base_field if isinstance(field, ArrayField) else field
            if getattr(inner, "choices", None):
                offenders.append(f"{model.__name__}.{field.name}")

    assert offenders == []
