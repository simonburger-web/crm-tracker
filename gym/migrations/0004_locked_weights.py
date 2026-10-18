from django.db import migrations, models


def old_outcomes_to_hold(apps, schema_editor):
    apps.get_model('gym', 'LiftLog').objects.exclude(outcome='up').update(outcome='hold')


class Migration(migrations.Migration):
    """Weights are locked and raised by session count, so reps and misses are no longer tracked."""

    dependencies = [
        ('gym', '0003_drop_replaced_lifts'),
    ]

    operations = [
        migrations.RemoveField(model_name='liftstate', name='misses'),
        migrations.AddField(
            model_name='liftstate', name='sessions', field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RemoveField(model_name='liftlog', name='reps'),
        migrations.RemoveField(model_name='liftlog', name='prev_misses'),
        migrations.AddField(
            model_name='liftlog', name='prev_sessions', field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(old_outcomes_to_hold, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='liftlog', name='outcome',
            field=models.CharField(choices=[('up', 'Weight up'), ('hold', 'Hold')], default='hold', max_length=10),
        ),
    ]
