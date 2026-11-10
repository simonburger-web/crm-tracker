from datetime import date

from django.urls import path, register_converter

from . import views


class DateConverter:
    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value):
        return date.fromisoformat(value)

    def to_url(self, value):
        return value.isoformat() if isinstance(value, date) else value


register_converter(DateConverter, "isodate")

app_name = "planner"

urlpatterns = [
    path("", views.today, name="today"),
    path("go/", views.go, name="go"),
    path("routines/", views.routines, name="routines"),
    path("routines/<int:pk>/<str:action>/", views.routine_action, name="routine_action"),
    path("task/<int:pk>/<str:action>/", views.task_action, name="task_action"),
    path("<isodate:day>/", views.day_view, name="day"),
    path("<isodate:day>/plan/", views.update_plan, name="update_plan"),
    path("<isodate:day>/review/", views.review, name="review"),
    path("<isodate:day>/tasks/", views.add_tasks, name="add_tasks"),
    path("<isodate:day>/schedule/", views.schedule, name="schedule"),
    path("<isodate:day>/carry/", views.carry_over, name="carry_over"),
    path("<isodate:day>/routines/", views.apply_routines, name="apply_routines"),
    path("<isodate:day>/routines/toggle/", views.toggle_routines, name="toggle_routines"),
]
