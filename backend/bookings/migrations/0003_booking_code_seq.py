from django.db import migrations


class Migration(migrations.Migration):
    """Sequence behind booking codes (PT24001, PT24002, …)."""

    dependencies = [("bookings", "0002_initial")]

    operations = [
        migrations.RunSQL(
            "CREATE SEQUENCE IF NOT EXISTS booking_code_seq START 24001;",
            "DROP SEQUENCE IF EXISTS booking_code_seq;",
        ),
    ]
