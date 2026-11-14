from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gym', '0007_active_session'),
    ]

    operations = [
        migrations.RemoveField(model_name='activesession', name='pending_weights'),
        migrations.AddField(
            model_name='activesession', name='sets', field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='liftlog', name='sets', field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name='liftlog', name='outcome',
            field=models.CharField(choices=[('up', 'Weight up'), ('hold', 'Hold'), ('down', 'Weight down')],
                                   default='hold', max_length=10),
        ),
        migrations.RemoveField(model_name='weightedit', name='sessions_needed'),
    ]
