from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

# decisions.md "Approval expiry": one-off sends last the send window; evergreen owned content 12 months;
# affiliate/partner placements and paid media 6 months (content outside our control drifts).
DEFAULTS: dict[str, tuple[str, int | None]] = {
    "email": ("send_window", None),
    "sms": ("send_window", None),
    "direct_mail": ("send_window", None),
    "landing_page": ("fixed_months", 12),
    "call_script": ("fixed_months", 12),
    "affiliate_page": ("fixed_months", 6),
    "paid_social": ("fixed_months", 6),
    "paid_search": ("fixed_months", 6),
    "display": ("fixed_months", 6),
}


def seed(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    policy = apps.get_model("reviews", "ExpiryPolicy")
    for channel, (rule, months) in DEFAULTS.items():
        policy.objects.update_or_create(channel=channel, defaults={"rule": rule, "months": months})


class Migration(migrations.Migration):
    dependencies = [("reviews", "0002_immutable_records")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
