from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Contact, ContactStatusLog


@receiver(pre_save, sender=Contact)
def _capture_old_status(sender, instance, **kwargs):
    # Contacts loaded from the DB already carry _loaded_status (see Contact.from_db).
    # Only fall back to a query for instances built by hand with an existing pk.
    if instance.pk and not hasattr(instance, '_loaded_status'):
        instance._loaded_status = (
            Contact.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
        )


@receiver(post_save, sender=Contact)
def _log_status_change(sender, instance, created, **kwargs):
    old_status = '' if created else getattr(instance, '_loaded_status', None)
    if old_status is not None and old_status != instance.status:
        ContactStatusLog.objects.create(
            contact=instance,
            from_status=old_status,
            to_status=instance.status,
            changed_by=getattr(instance, '_changed_by', None),
        )
    instance._loaded_status = instance.status
