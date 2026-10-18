from django.db import models

from .programme import DAYS_BY_SLUG


class LiftState(models.Model):
    """The locked working weight for one lift (slug from programme.LIFTS); only the calculator or the
    edit-weights page changes it."""
    slug = models.SlugField(max_length=50, unique=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    sessions = models.PositiveSmallIntegerField(default=0)  # completed at this weight since it last changed
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.slug}: {self.weight}'


class Workout(models.Model):
    """A completed programme day."""
    day = models.SlugField(max_length=10)
    completed_at = models.DateTimeField()

    class Meta:
        ordering = ['-completed_at', '-pk']

    def __str__(self):
        return f'{self.day} {self.completed_at:%Y-%m-%d}'

    @property
    def label(self):
        return DAYS_BY_SLUG[self.day].short if self.day in DAYS_BY_SLUG else self.day


class LiftLog(models.Model):
    """What was done for one lift in a workout, plus the state before it so the workout can be undone."""
    OUTCOME_CHOICES = [('up', 'Weight up'), ('hold', 'Hold')]

    workout = models.ForeignKey(Workout, on_delete=models.CASCADE, related_name='logs')
    slug = models.SlugField(max_length=50)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    outcome = models.CharField(max_length=10, choices=OUTCOME_CHOICES, default='hold')
    next_weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    prev_weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    prev_sessions = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['workout__completed_at', 'pk']


class WeightEdit(models.Model):
    """A manual override on the edit-weights page: the data for tuning each lift's overload rate later."""
    slug = models.SlugField(max_length=50, db_index=True)
    edited_at = models.DateTimeField(auto_now_add=True)
    old_weight = models.DecimalField(max_digits=6, decimal_places=2)
    new_weight = models.DecimalField(max_digits=6, decimal_places=2)
    # The weight being replaced was set by an automatic increase (not by an earlier manual edit).
    after_increase = models.BooleanField(default=False)
    sessions_at_weight = models.PositiveSmallIntegerField(default=0)  # completed at old_weight before the edit
    sessions_needed = models.PositiveSmallIntegerField(default=0)     # calculator's target at old_weight

    class Meta:
        ordering = ['-edited_at', '-pk']

    @property
    def change(self):
        return self.new_weight - self.old_weight
