from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from crm.models import Contact


class Command(BaseCommand):
    help = (
        'Assign unowned leads round-robin to the given usernames. With two users this keeps the '
        'old DriveOps split: even ids go to the first user, odd ids to the second.'
    )

    def add_arguments(self, parser):
        parser.add_argument('usernames', nargs='+')
        parser.add_argument('--pipeline', choices=[p for p, _ in Contact.PIPELINE_CHOICES])

    def handle(self, *args, usernames, pipeline=None, **options):
        User = get_user_model()
        users = []
        for username in usernames:
            try:
                users.append(User.objects.get(username=username))
            except User.DoesNotExist:
                raise CommandError(f'No user named "{username}". Create it first with createsuperuser.')

        contacts = Contact.objects.filter(owner__isnull=True)
        if pipeline:
            contacts = contacts.filter(pipeline=pipeline)

        total = 0
        for i, user in enumerate(users):
            ids = [pk for pk in contacts.values_list('pk', flat=True) if pk % len(users) == i]
            total += Contact.objects.filter(pk__in=ids).update(owner=user)
            self.stdout.write(f'  {user.username}: {len(ids)} lead(s)')
        self.stdout.write(self.style.SUCCESS(f'Done — assigned {total} lead(s).'))
