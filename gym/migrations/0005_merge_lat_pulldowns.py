from django.db import migrations


def forwards(apps, schema_editor):
    """Day 1's heavy lat pulldown now shares the day 3 lat pulldown weight."""
    LiftState = apps.get_model('gym', 'LiftState')
    heavy = LiftState.objects.filter(slug='heavy_lat_pulldown').first()
    if heavy:
        if LiftState.objects.filter(slug='lat_pulldown').exists():
            heavy.delete()
        else:
            heavy.slug = 'lat_pulldown'
            heavy.save()
    apps.get_model('gym', 'LiftLog').objects.filter(slug='heavy_lat_pulldown').update(slug='lat_pulldown')


class Migration(migrations.Migration):

    dependencies = [
        ('gym', '0004_locked_weights'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
