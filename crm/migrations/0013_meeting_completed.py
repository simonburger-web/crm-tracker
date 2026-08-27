from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0012_alter_contact_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='meeting',
            name='completed',
            field=models.BooleanField(default=False),
        ),
    ]
