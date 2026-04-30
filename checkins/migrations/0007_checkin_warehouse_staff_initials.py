from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("checkins", "0006_checkin_paper_form_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="checkin",
            name="warehouse_staff_initials",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
