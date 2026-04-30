from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("checkins", "0003_facility_street_address"),
    ]

    operations = [
        migrations.AlterField(
            model_name="smsmessage",
            name="delivery_status",
            field=models.CharField(
                choices=[("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed")],
                default="sent",
                max_length=10,
            ),
        ),
        migrations.CreateModel(
            name="OutboundSMS",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("to_number", models.CharField(max_length=20)),
                ("body", models.TextField()),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("sent", "Sent"), ("failed", "Failed")], default="pending", max_length=12)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("checkin", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="outbound_sms", to="checkins.checkin")),
                ("sms_message", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="outbound_sms", to="checkins.smsmessage")),
            ],
            options={
                "verbose_name": "outbound SMS job",
                "verbose_name_plural": "outbound SMS jobs",
                "ordering": ["created_at"],
            },
        ),
    ]
