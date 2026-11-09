from django import forms

from .models import DayPlan, Routine, Task

TIME_WIDGET = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
WEEKDAYS = [(str(i), d) for i, d in enumerate("Mon Tue Wed Thu Fri Sat Sun".split())]


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "priority", "category", "duration_minutes", "start_time"]
        widgets = {
            "start_time": TIME_WIDGET,
            "duration_minutes": forms.NumberInput(attrs={"min": 5, "max": 600, "step": 5}),
        }
        labels = {"duration_minutes": "Minutes", "start_time": "Start"}


class PlanForm(forms.ModelForm):
    class Meta:
        model = DayPlan
        fields = ["day_start", "day_end", "intention", "energy", "notes"]
        widgets = {
            "day_start": TIME_WIDGET,
            "day_end": TIME_WIDGET,
            "intention": forms.TextInput(attrs={"placeholder": "e.g. the proposal is sent to Acme"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Anything on your mind…"}),
        }

    def clean(self):
        data = super().clean()
        start, end = data.get("day_start"), data.get("day_end")
        if start and end and end <= start:
            raise forms.ValidationError("Your day has to end after it starts.")
        return data


class ReviewForm(forms.ModelForm):
    class Meta:
        model = DayPlan
        fields = ["wins", "improve", "rating"]
        widgets = {
            "wins": forms.Textarea(attrs={"rows": 2, "placeholder": "What went well?"}),
            "improve": forms.Textarea(attrs={"rows": 2, "placeholder": "One thing to change tomorrow"}),
        }
        labels = {"wins": "Wins", "rating": "Day rating (1–5)"}


class RoutineForm(forms.ModelForm):
    days = forms.MultipleChoiceField(choices=WEEKDAYS, widget=forms.CheckboxSelectMultiple, initial=list("01234"))

    class Meta:
        model = Routine
        fields = ["title", "start_time", "duration_minutes", "category", "active"]
        widgets = {
            "start_time": TIME_WIDGET,
            "duration_minutes": forms.NumberInput(attrs={"min": 5, "max": 600, "step": 5}),
        }
        labels = {"duration_minutes": "Minutes"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["days"].initial = list(self.instance.weekdays)

    def save(self, commit=True):
        self.instance.weekdays = "".join(sorted(self.cleaned_data["days"]))
        return super().save(commit)
