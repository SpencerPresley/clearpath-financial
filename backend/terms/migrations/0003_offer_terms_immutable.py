from django.db import migrations


class Migration(migrations.Migration):
    """Offer-terms versions are records: decisions quote them, so editing one would rewrite past approvals.

    The one allowed change is closing an open-ended range when the next version takes effect: same lower
    bound, an upper bound where there was none, every other column unchanged. DELETE is never allowed.
    """

    dependencies = [("terms", "0002_drop_enum_choices")]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION terms_offerterms_guard() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF TG_OP = 'UPDATE'
                        AND upper_inf(OLD.effective_range)
                        AND NOT upper_inf(NEW.effective_range)
                        AND lower(NEW.effective_range) = lower(OLD.effective_range)
                        AND lower_inc(NEW.effective_range) = lower_inc(OLD.effective_range)
                        AND (to_jsonb(NEW) - 'effective_range') = (to_jsonb(OLD) - 'effective_range')
                    THEN
                        RETURN NEW;
                    END IF;
                    RAISE EXCEPTION '% on terms_offerterms is not allowed: offer terms are immutable once '
                        'written (only closing an open range is permitted)', TG_OP
                        USING ERRCODE = 'restrict_violation';
                END;
                $$;
                CREATE TRIGGER terms_offerterms_guard BEFORE UPDATE OR DELETE ON terms_offerterms
                    FOR EACH ROW EXECUTE FUNCTION terms_offerterms_guard();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS terms_offerterms_guard ON terms_offerterms;
                DROP FUNCTION IF EXISTS terms_offerterms_guard();
            """,
        ),
    ]
