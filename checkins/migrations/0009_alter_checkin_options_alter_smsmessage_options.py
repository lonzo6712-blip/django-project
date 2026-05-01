from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("checkins", "0008_facility_slug"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="checkin",
            options={
                "ordering": ["status", "-arrival_time"],
                "verbose_name": "MonetteFarms check-in entry",
                "verbose_name_plural": "MonetteFarms check-in entries",
            },
        ),
        migrations.AlterModelOptions(
            name="smsmessage",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "driver text message",
                "verbose_name_plural": "driver text messages",
            },
        ),
    ]
