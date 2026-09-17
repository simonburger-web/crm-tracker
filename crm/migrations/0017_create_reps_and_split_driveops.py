from django.contrib.auth.hashers import make_password
from django.db import migrations

REPS = [
    ('simon', 'simon@altitudeinteractiveweb.com'),
    ('tristan', 'tristan@altitudeinteractiveweb.com'),
]


def create_reps(apps, schema_editor):
    """Create the two reps (no usable password - there are no logins) and split unowned DriveOps
    leads between them the way the old "Who are you?" picker did: even ids Simon, odd ids Tristan."""
    User = apps.get_model('auth', 'User')
    Contact = apps.get_model('crm', 'Contact')
    reps = []
    for username, email in REPS:
        user, _ = User.objects.get_or_create(
            username=username, defaults={'email': email, 'password': make_password(None)},
        )
        reps.append(user)

    unowned = Contact.objects.filter(pipeline='driveops', owner__isnull=True)
    for i, rep in enumerate(reps):
        ids = [pk for pk in unowned.values_list('pk', flat=True) if pk % len(reps) == i]
        Contact.objects.filter(pk__in=ids).update(owner=rep)


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0016_contact_lost_reason_note_author'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_reps, migrations.RunPython.noop),
    ]
