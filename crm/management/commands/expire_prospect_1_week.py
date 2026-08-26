from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from crm.models import Contact, ContactStatusLog


class Command(BaseCommand):
    help = 'Expire contacts in Prospect — 1 Week status that have been there for over 7 days'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=7)
        contacts = Contact.objects.filter(status='prospect_1_week')
        expired = 0
        for contact in contacts:
            log = ContactStatusLog.objects.filter(
                contact=contact,
                to_status='prospect_1_week',
            ).order_by('-changed_at').first()
            if log and log.changed_at <= cutoff:
                contact.status = 'inactive'
                contact.save()
                expired += 1
                self.stdout.write(f'  Expired: {contact.name}')
        self.stdout.write(self.style.SUCCESS(f'Done — expired {expired} contact(s).'))
