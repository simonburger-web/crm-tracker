from django import forms
from .models import Contact, Deal, Note, Meeting
from .utils import normalize_phone


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'email', 'phone', 'company', 'status', 'lost_reason', 'region', 'pipeline', 'owner', 'estimated_value']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full name'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'email@example.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+1 555 000 0000'}),
            'company': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Company name'}),
            'status': forms.Select(attrs={'class': 'form-input', 'id': 'id_status'}),
            'lost_reason': forms.Select(attrs={'class': 'form-input'}),
            'region': forms.Select(attrs={'class': 'form-input'}),
            'pipeline': forms.Select(attrs={'class': 'form-input'}),
            'owner': forms.Select(attrs={'class': 'form-input'}),
            'estimated_value': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '0.00', 'min': '0', 'step': '0.01'}),
        }
        labels = {
            'estimated_value': 'Estimated Value ($)',
            'lost_reason': 'Reason for going inactive',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['owner'].queryset = self.fields['owner'].queryset.filter(is_active=True)

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        phone_key = normalize_phone(phone)
        # Only check when the number is new or changed, so existing duplicates can still be edited.
        if phone_key and phone_key != self.instance.phone_normalized:
            existing = Contact.objects.filter(phone_normalized=phone_key).exclude(pk=self.instance.pk).first()
            if existing:
                raise forms.ValidationError(
                    f'This number already belongs to "{existing.name}" (lead #{existing.pk}, '
                    f'{existing.get_status_display()}).'
                )
        return phone

    def clean(self):
        cleaned = super().clean()
        error = Contact.lost_reason_error(cleaned.get('status'), cleaned.get('lost_reason'))
        if error and 'status' in cleaned:
            self.add_error('lost_reason', error)
        return cleaned

    def clean_status(self):
        status = self.cleaned_data['status']
        if self.instance.pk:
            error = self.instance.status_change_error(status)
            if error:
                raise forms.ValidationError(error)
        return status


class DealForm(forms.ModelForm):
    class Meta:
        model = Deal
        fields = ['title', 'contact', 'value', 'stage', 'close_date']
        labels = {
            'title': 'Closed deal',
            'contact': 'Lead',
        }
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Closed deal title'}),
            'contact': forms.Select(attrs={'class': 'form-input'}),
            'value': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '0.00'}),
            'stage': forms.Select(attrs={'class': 'form-input'}),
            'close_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        }


class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ['title', 'contact', 'meeting_type', 'scheduled_at', 'notes']
        labels = {
            'contact': 'Lead / Client',
            'scheduled_at': 'Date & Time',
            'meeting_type': 'Type',
        }
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Meeting title'}),
            'contact': forms.Select(attrs={'class': 'form-input'}),
            'meeting_type': forms.Select(attrs={'class': 'form-input'}),
            'scheduled_at': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': 'Notes...'}),
        }


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': 'Add a note...'}),
        }


class LeadsGeneratorForm(forms.Form):
    COUNTRY_CHOICES = [
        ('us', 'United States'),
        ('sa', 'South Africa'),
    ]

    country = forms.ChoiceField(
        choices=COUNTRY_CHOICES,
        initial='us',
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Country',
    )
    keyword = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. plumbing, dentist, auto repair'}),
        label='Keyword / Category',
    )
    state = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. CA or Gauteng'}),
        label='State / Province (optional)',
    )
    city = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. San Diego or Cape Town'}),
        label='City (optional)',
    )
    WEBSITE_FILTER_CHOICES = [
        ('no_website', 'No website'),
        ('any', 'Any'),
        ('with_website', 'With website'),
    ]

    max_results = forms.IntegerField(
        required=False,
        initial=25,
        min_value=1,
        max_value=500,
        widget=forms.NumberInput(attrs={'class': 'form-input'}),
        label='Max Results',
    )
    website_filter = forms.ChoiceField(
        choices=WEBSITE_FILTER_CHOICES,
        initial='no_website',
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Website',
    )
