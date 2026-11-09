from django.contrib import admin

from .models import DayPlan, Routine, Task


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0


@admin.register(DayPlan)
class DayPlanAdmin(admin.ModelAdmin):
    list_display = ("date", "intention", "rating")
    date_hierarchy = "date"
    inlines = [TaskInline]


@admin.register(Routine)
class RoutineAdmin(admin.ModelAdmin):
    list_display = ("title", "start_time", "duration_minutes", "weekdays", "active")
