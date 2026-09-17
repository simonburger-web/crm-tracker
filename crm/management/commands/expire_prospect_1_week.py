from django.core.management.base import BaseCommand

from crm.services import expire_one_week_prospects


class Command(BaseCommand):
    help = 'Expire contacts in Prospect — 1 Week status that have been there for over 7 days'

    def handle(self, *args, **options):
        expired = expire_one_week_prospects()
        for contact in expired:
            self.stdout.write(f'  Expired: {contact.name}')
        self.stdout.write(self.style.SUCCESS(f'Done — expired {len(expired)} contact(s).'))
