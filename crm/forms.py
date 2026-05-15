from django import forms
from .models import Contact, Deal, Note, Meeting


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'email', 'phone', 'company', 'status', 'region']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full name'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'email@example.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+1 555 000 0000'}),
            'company': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Company name'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
            'region': forms.Select(attrs={'class': 'form-input'}),
        }


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
    keyword = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. plumbing, dentist, auto repair'}),
        label='Keyword / Category',
    )
    state = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. CA'}),
        label='State (optional)',
    )
    city = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. San Diego'}),
        label='City (optional)',
    )
    max_results = forms.IntegerField(
        required=False,
        initial=25,
        min_value=1,
        max_value=500,
        widget=forms.NumberInput(attrs={'class': 'form-input'}),
        label='Max Results',
    )
