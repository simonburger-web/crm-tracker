from django.conf import settings
from django.db import models

from .utils import normalize_phone


class Contact(models.Model):
    STATUS_CHOICES = [
        ('lead', 'Lead'),
        ('call_back', 'Call Back'),
        ('call_back_no_answer', 'Call Back - No Answer'),
        ('prospect', 'Prospect'),
        ('prospect_1_week', 'Prospect — 1 Week'),
        ('customer', 'Customer'),
        ('inactive', 'Inactive'),
    ]

    # Statuses that mean "someone owes this lead a follow-up".
    FOLLOW_UP_STATUSES = ('call_back', 'call_back_no_answer', 'prospect', 'prospect_1_week')
    # A lead in this status can only be promoted to customer; it auto-expires after 7 days.
    LOCKED_STATUS = 'prospect_1_week'
    LOCKED_STATUS_DAYS = 7

    REGION_CHOICES = [
        ('us', 'US'),
        ('sa', 'SA'),
    ]

    PIPELINE_CHOICES = [
        ('general', 'General'),
        ('driveops', 'DriveOps'),
    ]

    # Why a lead went inactive (Pipedrive-style "lost reason"). Required when marking inactive.
    LOST_REASON_CHOICES = [
        ('no_answer', 'Never answered'),
        ('not_interested', 'Not interested'),
        ('has_system', 'Already uses a system'),
        ('price', 'Too expensive'),
        ('closed', 'Business closed'),
        ('wrong_number', 'Wrong / invalid number'),
        ('expired', 'Prospect — 1 Week expired'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    company = models.CharField(max_length=200, blank=True)
    phone_normalized = models.CharField(max_length=30, blank=True, db_index=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='lead', db_index=True)
    region = models.CharField(max_length=5, choices=REGION_CHOICES, default='us')
    pipeline = models.CharField(max_length=20, choices=PIPELINE_CHOICES, default='general', db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='contacts',
    )
    estimated_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    lost_reason = models.CharField(max_length=20, choices=LOST_REASON_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'

    def __str__(self):
        return self.name

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        # Remember the status as loaded so the status-log signal needs no extra query.
        if 'status' in instance.__dict__:
            instance._loaded_status = instance.status
        return instance

    def save(self, *args, **kwargs):
        self.phone_normalized = normalize_phone(self.phone)
        if self.status != 'inactive':
            self.lost_reason = ''
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)
            if 'phone' in update_fields:
                update_fields.add('phone_normalized')
            if 'status' in update_fields:
                update_fields.add('lost_reason')
            kwargs['update_fields'] = update_fields
        super().save(*args, **kwargs)

    def status_change_error(self, new_status):
        """Return an error message if moving to new_status is not allowed, else None."""
        if new_status not in dict(self.STATUS_CHOICES):
            return 'Invalid status.'
        old_status = getattr(self, '_loaded_status', None)
        if old_status == self.LOCKED_STATUS and new_status not in (self.LOCKED_STATUS, 'customer'):
            return 'Prospect — 1 Week leads can only be moved to Customer.'
        return None

    @classmethod
    def lost_reason_error(cls, new_status, lost_reason):
        if new_status == 'inactive' and lost_reason not in dict(cls.LOST_REASON_CHOICES):
            return 'Pick a reason for marking this lead inactive.'
        return None


class Deal(models.Model):
    STAGE_CHOICES = [
        ('prospecting', 'Prospecting'),
        ('proposal', 'Proposal'),
        ('negotiation', 'Negotiation'),
        ('won', 'Won'),
        ('lost', 'Lost'),
    ]

    title = models.CharField(max_length=200)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='deals')
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='prospecting')
    close_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Closed Deal'
        verbose_name_plural = 'Closed Deals'

    def __str__(self):
        return self.title


class Meeting(models.Model):
    MEETING_TYPE_CHOICES = [
        ('call', 'Call'),
        ('video', 'Video Call'),
        ('in_person', 'In Person'),
        ('email', 'Email'),
    ]

    title = models.CharField(max_length=200)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='meetings')
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPE_CHOICES, default='call')
    scheduled_at = models.DateTimeField()
    notes = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_at']

    def __str__(self):
        return f"{self.title} – {self.contact.name}"


class TodoBlock(models.Model):
    COLOR_CHOICES = [
        ('blue', 'Blue'),
        ('green', 'Green'),
        ('orange', 'Orange'),
        ('purple', 'Purple'),
        ('red', 'Red'),
        ('yellow', 'Yellow'),
    ]
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    title = models.CharField(max_length=200)
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default='blue')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"{self.title} ({self.date} {self.start_time:%H:%M}–{self.end_time:%H:%M})"


class SavedRecipient(models.Model):
    email = models.EmailField(unique=True)
    label = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['email']

    def __str__(self):
        return self.label or self.email


class Unsubscribe(models.Model):
    email = models.EmailField(unique=True)
    unsubscribed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-unsubscribed_at']

    def __str__(self):
        return self.email


class Note(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='notes', null=True, blank=True)
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name='notes', null=True, blank=True)
    body = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.body[:50]


class ContactStatusLog(models.Model):
    """Records every status change on a Contact, for analytics."""
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='status_logs')
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='status_changes',
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['changed_at']

    def __str__(self):
        return f'{self.contact.name}: {self.from_status} → {self.to_status}'


class EmailCampaign(models.Model):
    """One mass-email send. Individual deliveries are tracked as EmailSend rows."""
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sending', 'Sending'),
        ('done', 'Done'),
    ]
    subject = models.CharField(max_length=300)
    body = models.TextField()
    from_email = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    skipped_unsubscribed = models.PositiveIntegerField(default=0)
    over_cap = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.subject


class EmailSend(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    campaign = models.ForeignKey(EmailCampaign, on_delete=models.CASCADE, related_name='sends')
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='email_sends')
    email = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['pk']

    def __str__(self):
        return f'{self.email} ({self.status})'
