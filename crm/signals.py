from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Contact, ContactStatusLog

_pending_status = {}


@receiver(pre_save, sender=Contact)
def _capture_old_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Contact.objects.get(pk=instance.pk)
            _pending_status[instance.pk] = old.status
        except Contact.DoesNotExist:
            pass


@receiver(post_save, sender=Contact)
def _log_status_change(sender, instance, created, **kwargs):
    if created:
        ContactStatusLog.objects.create(
            contact=instance,
            from_status='',
            to_status=instance.status,
        )
        return
    old_status = _pending_status.pop(instance.pk, None)
    if old_status is not None and old_status != instance.status:
        ContactStatusLog.objects.create(
            contact=instance,
            from_status=old_status,
            to_status=instance.status,
        )
