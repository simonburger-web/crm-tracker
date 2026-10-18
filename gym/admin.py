from django.contrib import admin

from .models import LiftLog, LiftState, Workout


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
