from django.db import migrations

# Replaced or dropped lifts whose weights don't carry over: Day 2 and 4 now use standing calf raises and a
# standing leg curl, Day 3 a Bayesian cable curl instead of DB curls, and planks are gone.
REPLACED = ('leg_press_calf', 'lying_leg_curl', 'db_curl', 'db_calf_raise', 'plank')


def forwards(apps, schema_editor):
    apps.get_model('gym', 'LiftState').objects.filter(slug__in=REPLACED).delete()
    apps.get_model('gym', 'LiftLog').objects.filter(slug__in=REPLACED).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('gym', '0002_number_days_drop_weighted_pullup'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
