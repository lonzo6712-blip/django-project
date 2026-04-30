from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("checkins", "0002_smsmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="facility",
            name="street_address",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
