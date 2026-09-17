from django.db import migrations

from crm.utils import normalize_phone


def backfill(apps, schema_editor):
    Contact = apps.get_model('crm', 'Contact')
    # DriveOps used to be identified by company name; make it an explicit pipeline.
    Contact.objects.filter(company__icontains='driving school').update(pipeline='driveops')

    batch = []
    for contact in Contact.objects.exclude(phone='').only('pk', 'phone').iterator():
        contact.phone_normalized = normalize_phone(contact.phone)
        batch.append(contact)
        if len(batch) >= 500:
            Contact.objects.bulk_update(batch, ['phone_normalized'])
            batch = []
    if batch:
        Contact.objects.bulk_update(batch, ['phone_normalized'])


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0014_contact_pipeline_owner_email_campaigns'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
