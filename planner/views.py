from datetime import date as date_cls, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import PlanForm, ReviewForm, RoutineForm, TaskForm
from .models import Category, DayPlan, Priority, Routine, Task
from .parsing import parse_line
from .scheduling import auto_schedule, capacity, timeline, to_min


# Same clock as the gym: "today", "tomorrow" and the now-marker use local time, not the server's UTC.
PLANNER_TZ = ZoneInfo("Africa/Johannesburg")


def planner_view(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        with timezone.override(PLANNER_TZ):
            return view(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- helpers

def _now_minutes():
    now = timezone.localtime()
    return now.hour * 60 + now.minute


def _next_order(plan):
    return (plan.tasks.aggregate(m=Max("order"))["m"] or 0) + 1


def _apply_routines(plan):
    existing = set(plan.tasks.exclude(routine=None).values_list("routine_id", flat=True))
    added = 0
    for r in Routine.objects.filter(active=True):
        if r.runs_on(plan.date) and r.id not in existing:
            Task.objects.create(
                plan=plan, routine=r, title=r.title, start_time=r.start_time,
                duration_minutes=r.duration_minutes, category=r.category,
                priority=Priority.SHOULD, order=_next_order(plan),
            )
            added += 1
    return added


def get_plan(day):
    plan, created = DayPlan.objects.get_or_create(date=day)
    if created:
        # Inherit working hours from your most recent plan.
        last = DayPlan.objects.exclude(pk=plan.pk).filter(date__lt=day).first()
        if last:
            plan.day_start, plan.day_end = last.day_start, last.day_end
            plan.save(update_fields=["day_start", "day_end"])
        _apply_routines(plan)
    return plan


def _back(plan, anchor=""):
    url = reverse("planner:day", args=[plan.date])
    return redirect(f"{url}#{anchor}" if anchor else url)


def _own_task(request, pk):
    return get_object_or_404(Task.objects.select_related("plan"), pk=pk)


# ---------------------------------------------------------------- pages

@planner_view
def today(request):
    return redirect("planner:day", day=timezone.localdate())


@planner_view
def go(request):
    try:
        day = date_cls.fromisoformat(request.GET.get("d", ""))
    except ValueError:
        day = timezone.localdate()
    return redirect("planner:day", day=day)


@planner_view
def day_view(request, day):
    plan = get_plan(day)
    tasks = list(plan.tasks.all())
    real_today = timezone.localdate()
    is_today = day == real_today
    now_min = _now_minutes() if is_today else None

    groups = [
        {"value": p.value, "label": p.label, "tasks": [t for t in tasks if t.priority == p.value]}
        for p in Priority
    ]
    musts = groups[0]["tasks"]
    frog = next((t for t in tasks if t.is_frog), None)

    prev_plan = (
        DayPlan.objects.filter(date__lt=day, tasks__done=False, tasks__routine=None)
        .distinct().first()
    )
    carry_count = prev_plan.tasks.filter(done=False, routine=None).count() if prev_plan else 0

    done = sum(t.done for t in tasks)
    evening = is_today and timezone.localtime().hour >= 17

    return render(request, "planner/day.html", {
        "plan": plan,
        "tasks": tasks,
        "groups": groups,
        "frog": frog,
        "must_done": sum(t.done for t in musts),
        "must_total": len(musts),
        "too_many_musts": len(musts) > 3,
        "done": done,
        "total": len(tasks),
        "unscheduled": sum(1 for t in tasks if t.start_time is None and not t.done and t.duration_minutes is not None),
        "anytime": [t for t in tasks if t.is_anytime],
        "cap": capacity(plan, tasks),
        "timeline": timeline(plan, tasks, now_min),
        "is_today": is_today,
        "is_tomorrow": day == real_today + timedelta(days=1),
        "is_past": day < real_today,
        "prev_day": day - timedelta(days=1),
        "next_day": day + timedelta(days=1),
        "real_today": real_today,
        "real_tomorrow": real_today + timedelta(days=1),
        "evening": evening,
        "show_plan_tomorrow": evening,
        "carry_plan": prev_plan,
        "carry_count": carry_count,
        "plan_form": PlanForm(instance=plan),
        "review_form": ReviewForm(instance=plan),
        "has_routines": Routine.objects.filter(active=True).exists(),
        "priorities": Priority.choices,
        "categories": Category.choices,
    })


# ---------------------------------------------------------------- plan actions

@planner_view
@require_POST
def update_plan(request, day):
    plan = get_plan(day)
    fields = [f for f in PlanForm.Meta.fields if f in request.POST]
    Form = modelform_factory(DayPlan, form=PlanForm, fields=fields)
    form = Form(request.POST, instance=plan)
    if form.is_valid():
        form.save()
        messages.success(request, "Saved.")
    else:
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
    return _back(plan, request.POST.get("anchor", ""))


@planner_view
@require_POST
def review(request, day):
    plan = get_plan(day)
    form = ReviewForm(request.POST, instance=plan)
    if form.is_valid():
        form.save()
        messages.success(request, "Day closed out. Now plan tomorrow while it's fresh.")
    return _back(plan, "review")


@planner_view
@require_POST
def add_tasks(request, day):
    plan = get_plan(day)
    parsed = [p for p in (parse_line(l) for l in request.POST.get("lines", "").splitlines()) if p]
    order = _next_order(plan)
    with transaction.atomic():
        for i, data in enumerate(parsed):
            if data["is_frog"]:
                plan.tasks.update(is_frog=False)
            Task.objects.create(plan=plan, order=order + i, **data)
    if parsed:
        messages.success(request, f"Added {len(parsed)} task{'s' if len(parsed) != 1 else ''}.")
    return _back(plan, "dump")


@planner_view
@require_POST
def schedule(request, day):
    plan = get_plan(day)
    tasks = list(plan.tasks.all())
    if request.POST.get("action") == "clear":
        n = (plan.tasks.filter(done=False, routine=None).exclude(start_time=None)
             .exclude(duration_minutes=None).update(start_time=None))
        messages.info(request, f"Cleared times on {n} task{'s' if n != 1 else ''}. Routines and checkpoints kept.")
        return _back(plan, "timeblock")

    earliest = _now_minutes() if plan.date == timezone.localdate() else None
    placed, overflow = auto_schedule(tasks, plan.day_start, plan.day_end, earliest)
    Task.objects.bulk_update(placed, ["start_time"])
    if placed:
        messages.success(request, f"Time-blocked {len(placed)} task{'s' if len(placed) != 1 else ''}.")
    if overflow:
        names = ", ".join(t.title for t in overflow[:3]) + ("…" if len(overflow) > 3 else "")
        messages.warning(
            request,
            f"{len(overflow)} didn't fit ({names}). Cut them, shorten them, or push them to tomorrow.",
        )
    if not placed and not overflow:
        messages.info(request, "Nothing left to schedule.")
    return _back(plan, "timeblock")


@planner_view
@require_POST
def carry_over(request, day):
    plan = get_plan(day)
    source = get_object_or_404(DayPlan, pk=request.POST.get("from"), date__lt=day)
    order = _next_order(plan)
    moved = 0
    for i, t in enumerate(source.tasks.filter(done=False, routine=None)):
        t.plan, t.order, t.start_time = plan, order + i, None
        t.carried_count += 1
        if t.is_frog and plan.tasks.filter(is_frog=True).exists():
            t.is_frog = False
        t.save()
        moved += 1
    messages.success(request, f"Brought over {moved} unfinished task{'s' if moved != 1 else ''}.")
    return _back(plan, "prioritise")


@planner_view
@require_POST
def apply_routines(request, day):
    plan = get_plan(day)
    n = _apply_routines(plan)
    messages.info(request, f"Added {n} routine block{'s' if n != 1 else ''}." if n else "Routines already on the plan.")
    return _back(plan, "timeblock")


# ---------------------------------------------------------------- task actions

@planner_view
@require_POST
def task_action(request, pk, action):
    task = _own_task(request, pk)
    plan = task.plan
    anchor = f"task-{task.pk}"

    if action == "toggle":
        task.done = not task.done
        task.save(update_fields=["done"])
    elif action == "frog":
        with transaction.atomic():
            becoming = not task.is_frog
            plan.tasks.update(is_frog=False)
            task.is_frog = becoming
            if becoming and task.priority != Priority.MUST:
                task.priority = Priority.MUST
            task.save(update_fields=["is_frog", "priority"])
    elif action == "edit":
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
        else:
            messages.error(request, "Couldn't save that task – check the fields.")
    elif action == "defer":
        target = get_plan(plan.date + timedelta(days=1))
        task.plan, task.start_time, task.done, task.is_frog = target, None, False, False
        task.carried_count += 1
        task.order = _next_order(target)
        task.save()
        messages.info(request, f"Moved “{task.title}” to {target.date:%a %d %b}.")
        anchor = "prioritise"
    elif action == "unschedule":
        task.start_time = None
        task.save(update_fields=["start_time"])
        anchor = "timeblock"
    elif action == "delete":
        task.delete()
        anchor = "prioritise"
    return _back(plan, anchor)


# ---------------------------------------------------------------- routines

@planner_view
def routines(request):
    if request.method == "POST":
        form = RoutineForm(request.POST)
        if form.is_valid():
            r = form.save()
            messages.success(request, f"Routine “{r.title}” added. It'll appear on new days automatically.")
            return redirect("planner:routines")
    else:
        form = RoutineForm()
    items = [(r, RoutineForm(instance=r, prefix=f"r{r.pk}")) for r in Routine.objects.all()]
    return render(request, "planner/routines.html", {"form": form, "items": items})


@planner_view
@require_POST
def routine_action(request, pk, action):
    r = get_object_or_404(Routine, pk=pk)
    if action == "delete":
        r.delete()
        messages.info(request, "Routine removed.")
    elif action == "edit":
        form = RoutineForm(request.POST, instance=r, prefix=f"r{r.pk}")
        if form.is_valid():
            form.save()
            messages.success(request, "Routine updated (applies to newly created days).")
        else:
            messages.error(request, "Couldn't save – check the fields.")
    return redirect("planner:routines")
