"""Business logic shared by views and management commands."""
import random
import threading
import time
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail
from django.db import connection, transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from .models import Contact, ContactStatusLog, Deal, EmailCampaign, EmailSend, Meeting, Note

EMAIL_FOOTER = (
    "\n\n---\n"
    "Altitude Interactive (Pty) Ltd, 8 Jamaican Music Avenue, Pretoria, 0081, South Africa\n"
    "Don't want these emails? Unsubscribe here: {unsubscribe_url}"
)


def status_since_subquery():
    """Annotation: when the contact most recently entered its current status."""
    return Subquery(
        ContactStatusLog.objects.filter(contact=OuterRef('pk'), to_status=OuterRef('status'))
        .order_by('-changed_at')
        .values('changed_at')[:1]
    )


def expire_one_week_prospects(now=None):
    """Move Prospect — 1 Week leads that have sat there for 7+ days to Inactive.

    Idempotent and cheap (one query when nothing is due), so it runs on DriveOps page
    loads as well as from the expire_prospect_1_week management command.
    """
    now = now or timezone.now()
    cutoff = now - timedelta(days=Contact.LOCKED_STATUS_DAYS)
    due = Contact.objects.filter(status=Contact.LOCKED_STATUS).annotate(since=status_since_subquery()).filter(
        since__lte=cutoff
    )
    expired = []
    for contact in due:
        contact.status = 'inactive'
        contact.lost_reason = 'expired'
        contact.save(update_fields=['status', 'updated_at'])  # save() adds lost_reason
        expired.append(contact)
    return expired


def change_status(contact, new_status, user, lost_reason=''):
    """Validate and apply a status change, attributing it to user. Returns an error string or None.

    Marking a lead inactive requires a lost_reason (one of Contact.LOST_REASON_CHOICES).
    """
    error = contact.status_change_error(new_status) or Contact.lost_reason_error(new_status, lost_reason)
    if error:
        return error
    contact.status = new_status
    if new_status == 'inactive':
        contact.lost_reason = lost_reason
    contact._changed_by = user
    if contact.owner_id is None:
        contact.owner = user
    contact.save()
    return None


# Fields copied onto the surviving contact when it has no value of its own.
_MERGE_FILL_FIELDS = ('email', 'company', 'estimated_value', 'owner_id')


@transaction.atomic
def merge_contacts(survivor, duplicates):
    """Fold duplicates into survivor (HubSpot/Pipedrive-style merge) and delete them.

    Notes, meetings, deals, status history and email sends move to the survivor, and any
    blank survivor fields are filled from the duplicates, so no work is lost.
    """
    dupe_ids = [d.pk for d in duplicates if d.pk != survivor.pk]
    if not dupe_ids:
        return 0
    for model in (Note, Meeting, Deal, ContactStatusLog, EmailSend):
        model.objects.filter(contact_id__in=dupe_ids).update(contact=survivor)

    changed = []
    for dupe in sorted(duplicates, key=lambda d: d.created_at):
        for field in _MERGE_FILL_FIELDS:
            if not getattr(survivor, field) and getattr(dupe, field):
                setattr(survivor, field, getattr(dupe, field))
                changed.append(field.removesuffix('_id'))
    if changed:
        survivor.save(update_fields={*changed, 'updated_at'})
    Contact.objects.filter(pk__in=dupe_ids).delete()
    return len(dupe_ids)


def process_campaign(campaign_id, base_url):
    """Send every pending EmailSend in a campaign, pausing between messages."""
    campaign = EmailCampaign.objects.get(pk=campaign_id)
    campaign.status = 'sending'
    campaign.save(update_fields=['status'])
    delay = getattr(settings, 'CRM_EMAIL_DELAY_SECONDS', (4, 8))

    pending = list(campaign.sends.filter(status='pending').select_related('contact'))
    for i, send in enumerate(pending):
        contact = send.contact
        name = (contact.name if contact else '') or 'there'
        company = (contact.company if contact else '') or 'your business'
        body = campaign.body.replace('{name}', name).replace('{company}', company)
        unsubscribe_url = f"{base_url.rstrip('/')}/unsubscribe/{quote(send.email, safe='@')}/"
        try:
            send_mail(
                campaign.subject,
                body + EMAIL_FOOTER.format(unsubscribe_url=unsubscribe_url),
                campaign.from_email,
                [send.email],
                fail_silently=False,
            )
            send.status = 'sent'
            send.sent_at = timezone.now()
        except Exception as exc:  # SMTP errors vary widely; record and move on
            send.status = 'failed'
            send.error = str(exc)[:1000]
        send.save(update_fields=['status', 'sent_at', 'error'])

        if i < len(pending) - 1 and delay:
            time.sleep(random.uniform(*delay))

    campaign.status = 'done'
    campaign.save(update_fields=['status'])


def start_campaign(campaign, base_url):
    """Send a campaign without blocking the request (Heroku kills requests after 30s).

    base_url is the site root (e.g. https://crm.example.com) used to build unsubscribe links.
    """
    if not getattr(settings, 'CRM_EMAIL_ASYNC', True):
        process_campaign(campaign.pk, base_url)
        return

    def run():
        try:
            process_campaign(campaign.pk, base_url)
        finally:
            connection.close()  # connections are per-thread; don't leak this one

    threading.Thread(target=run, daemon=True, name=f'email-campaign-{campaign.pk}').start()
