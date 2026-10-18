from django.contrib import admin

from .models import LiftLog, LiftState, WeightEdit, Workout


class LiftLogInline(admin.TabularInline):
    model = LiftLog
    extra = 0


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ('day', 'completed_at')
    inlines = [LiftLogInline]


@admin.register(LiftState)
class LiftStateAdmin(admin.ModelAdmin):
    list_display = ('slug', 'weight', 'sessions', 'updated_at')


@admin.register(WeightEdit)
class WeightEditAdmin(admin.ModelAdmin):
    list_display = ('slug', 'edited_at', 'old_weight', 'new_weight', 'after_increase', 'sessions_at_weight',
                    'sessions_needed')
    list_filter = ('slug', 'after_increase')
