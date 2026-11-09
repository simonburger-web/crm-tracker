from datetime import time

from django.db import models


class Priority(models.IntegerChoices):
    MUST = 1, "Must do"
    SHOULD = 2, "Should do"
    COULD = 3, "Could do"


class Category(models.TextChoices):
    DEEP = "deep", "Deep work"
    ADMIN = "admin", "Admin & email"
    MEETING = "meeting", "Calls & meetings"
    PERSONAL = "personal", "Personal"


class DayPlan(models.Model):
    date = models.DateField(unique=True)
    day_start = models.TimeField(default=time(8, 0))
    day_end = models.TimeField(default=time(18, 0))
    intention = models.CharField("Today is a win if…", max_length=200, blank=True)
    energy = models.PositiveSmallIntegerField(null=True, blank=True, choices=[(i, str(i)) for i in range(1, 6)])
    notes = models.TextField(blank=True)
    # Evening shutdown review
    wins = models.TextField(blank=True)
    improve = models.TextField("Do differently tomorrow", blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True, choices=[(i, str(i)) for i in range(1, 6)])
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return str(self.date)


class Routine(models.Model):
    """A recurring block (gym, lunch, standup) auto-added to new day plans."""

    title = models.CharField(max_length=200)
    start_time = models.TimeField(null=True, blank=True, help_text="Leave empty for an anytime habit")
    duration_minutes = models.PositiveIntegerField(null=True, blank=True, help_text="Leave empty for a checkpoint like 'out of bed'")
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.PERSONAL)
    weekdays = models.CharField(max_length=7, default="01234", help_text="Mon=0 … Sun=6")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["start_time"]

    def __str__(self):
        return self.title

    def runs_on(self, date):
        return str(date.weekday()) in self.weekdays

    @property
    def weekday_labels(self):
        names = "Mon Tue Wed Thu Fri Sat Sun".split()
        if self.weekdays == "01234":
            return "Weekdays"
        if self.weekdays == "56":
            return "Weekends"
        if self.weekdays == "0123456":
            return "Every day"
        return ", ".join(names[int(d)] for d in self.weekdays)


class Task(models.Model):
    plan = models.ForeignKey(DayPlan, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    priority = models.PositiveSmallIntegerField(choices=Priority.choices, default=Priority.SHOULD)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.ADMIN)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)  # empty = no set length
    start_time = models.TimeField(null=True, blank=True)
    is_frog = models.BooleanField(default=False)
    done = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    carried_count = models.PositiveSmallIntegerField(default=0)
    routine = models.ForeignKey(Routine, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["priority", "order", "id"]

    def __str__(self):
        return self.title

    @property
    def is_timed(self):
        """Has a length, so it takes up room in the day."""
        return self.duration_minutes is not None

    @property
    def is_checkpoint(self):
        """A moment ("out of bed @7am"), not a block of time."""
        return self.start_time is not None and self.duration_minutes is None

    @property
    def is_anytime(self):
        return self.start_time is None and self.duration_minutes is None

    @property
    def end_minutes(self):
        if self.start_time is None:
            return None
        return self.start_time.hour * 60 + self.start_time.minute + (self.duration_minutes or 0)
