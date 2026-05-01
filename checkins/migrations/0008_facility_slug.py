from django.db import migrations, models
from django.utils.text import slugify


def backfill_facility_slugs(apps, schema_editor):
    Facility = apps.get_model("checkins", "Facility")
    for facility in Facility.objects.all().order_by("id"):
        if facility.slug:
            continue
        base_slug = slugify(facility.name) or "facility"
        slug = base_slug
        index = 2
        while Facility.objects.exclude(pk=facility.pk).filter(slug=slug).exists():
            slug = f"{base_slug}-{index}"
            index += 1
        facility.slug = slug
        facility.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("checkins", "0007_checkin_warehouse_staff_initials"),
    ]

    operations = [
        migrations.AddField(
            model_name="facility",
            name="slug",
            field=models.SlugField(blank=True, max_length=140, null=True),
        ),
        migrations.RunPython(backfill_facility_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="facility",
            name="slug",
            field=models.SlugField(blank=True, max_length=140, unique=True),
        ),
    ]
