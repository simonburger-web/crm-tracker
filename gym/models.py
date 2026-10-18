from django.db import models


class LiftState(models.Model):
    """The working weight to load next time for one lift (slug from programme.LIFTS)."""
    slug = models.SlugField(max_length=50, unique=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    misses = models.PositiveSmallIntegerField(default=0)  # consecutive sessions below the rep range
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


class LiftLog(models.Model):
    """What was done for one lift in a workout, plus the state before it so the workout can be undone."""
    OUTCOME_CHOICES = [('up', 'Weight up'), ('hold', 'Hold'), ('miss', 'Missed'), ('deload', 'Deload')]

    workout = models.ForeignKey(Workout, on_delete=models.CASCADE, related_name='logs')
    slug = models.SlugField(max_length=50)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    reps = models.JSONField(default=list)  # reps per set (seconds for timed holds)
    outcome = models.CharField(max_length=10, choices=OUTCOME_CHOICES, default='hold')
    next_weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    prev_weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    prev_misses = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['workout__completed_at', 'pk']
