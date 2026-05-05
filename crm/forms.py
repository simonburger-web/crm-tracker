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
