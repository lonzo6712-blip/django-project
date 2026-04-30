from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("checkins", "0004_outboundsms_and_sms_queued"),
    ]

    operations = [
        migrations.AddField(
            model_name="outboundsms",
            name="next_attempt_at",
            field=models.DateTimeField(default=timezone.now),
        ),
    ]
