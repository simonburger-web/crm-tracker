from django.db import migrations

DAY_SLUGS = {'mon': 'day1', 'tue': 'day2', 'thu': 'day3', 'fri': 'day4'}


def forwards(apps, schema_editor):
    Workout = apps.get_model('gym', 'Workout')
    for old, new in DAY_SLUGS.items():
        Workout.objects.filter(day=old).update(day=new)
    # Weighted pull-ups were replaced by heavy lat pulldowns; belt weight doesn't carry over.
    apps.get_model('gym', 'LiftState').objects.filter(slug='weighted_pullup').delete()
    apps.get_model('gym', 'LiftLog').objects.filter(slug='weighted_pullup').delete()


def backwards(apps, schema_editor):
    Workout = apps.get_model('gym', 'Workout')
    for old, new in DAY_SLUGS.items():
        Workout.objects.filter(day=new).update(day=old)


class Migration(migrations.Migration):

    dependencies = [
        ('gym', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
