from django.db import models


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

    REGION_CHOICES = [
        ('us', 'US'),
        ('sa', 'SA'),
    ]

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    company = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='lead')
    region = models.CharField(max_length=5, choices=REGION_CHOICES, default='us')
    estimated_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'

    def __str__(self):
        return self.name


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
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['changed_at']

    def __str__(self):
        return f'{self.contact.name}: {self.from_status} → {self.to_status}'
