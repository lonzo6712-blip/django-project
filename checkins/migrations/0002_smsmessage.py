from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("checkins", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SMSMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("to_number", models.CharField(max_length=20)),
                ("from_number", models.CharField(blank=True, max_length=20)),
                ("body", models.TextField()),
                ("delivery_status", models.CharField(choices=[("sent", "Sent"), ("failed", "Failed")], default="sent", max_length=10)),
                ("provider_message_id", models.CharField(blank=True, max_length=120)),
                ("error_message", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("checkin", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="sms_messages", to="checkins.checkin")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
