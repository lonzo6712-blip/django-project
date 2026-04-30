from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("checkins", "0005_outboundsms_next_attempt_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="checkin",
            name="actual_temperature",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="checkin",
            name="bol_number",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="checkin",
            name="destination_delivery_address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="checkin",
            name="driver_signature",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="checkin",
            name="temperature_setpoint",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="checkin",
            name="trailer_license_plate",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="checkin",
            name="weight_in_out",
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
