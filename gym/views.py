from datetime import timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import LiftLog, LiftState, Workout
from .programme import DAYS, DAYS_BY_SLUG, LIFTS
from .progression import DELOADED, UP, estimated_1rm, next_weight, plates_per_side

# The gym clock: "today" and workout dates are shown in local time, not the server's UTC.
GYM_TZ = ZoneInfo('Africa/Johannesburg')


def _activate_tz(view):
    def wrapper(request, *args, **kwargs):
        with timezone.override(GYM_TZ):
            return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _states():
    return {s.slug: s for s in LiftState.objects.all()}


def _last_logs():
    """Most recent log per lift slug."""
    last = {}
    for log in LiftLog.objects.select_related('workout').order_by('workout__completed_at', 'pk'):
        last[log.slug] = log
    return last


def _next_day(last_workout):
    """The day after the last one completed, rotating Mon → Tue → Thu → Fri."""
    if last_workout is None:
        today = timezone.localdate().weekday()
        return next((d for d in DAYS if d.weekday >= today), DAYS[0])
    idx = next((i for i, d in enumerate(DAYS) if d.slug == last_workout.day), -1)
    return DAYS[(idx + 1) % len(DAYS)]


def _fmt(weight):
    """100.00 -> '100', 12.50 -> '12.5'."""
    if weight is None:
        return ''
    return f'{weight.normalize():f}'


def _parse_weight(raw):
    raw = (raw or '').strip().replace(',', '.')
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def _parse_reps(raw):
    try:
        value = int((raw or '').strip())
    except ValueError:
        return None
    return value if value >= 0 else None


@_activate_tz
def home(request):
    workouts = list(Workout.objects.prefetch_related('logs')[:12])
    last_workout = workouts[0] if workouts else None
    up_next = _next_day(last_workout)
    last_by_day = {}
    for slug, completed_at in Workout.objects.values_list('day', 'completed_at'):
        last_by_day.setdefault(slug, completed_at)

    states = _states()
    last_logs = _last_logs()
    lifts = []
    for lift in LIFTS.values():
        if lift.timed:
            continue
        state = states.get(lift.slug)
        log = last_logs.get(lift.slug)
        lifts.append({
            'lift': lift,
            'weight': _fmt(state.weight) if state else '',
            'outcome': log.outcome if log else '',
            'e1rm': _fmt(estimated_1rm(log.weight, log.reps)) if log and lift.equipment in ('barbell', 'dumbbell') else '',
        })

    days = [{'day': d, 'last': last_by_day.get(d.slug), 'is_next': d == up_next} for d in DAYS]
    return render(request, 'gym/home.html', {
        'days': days, 'up_next': up_next, 'lifts': lifts, 'workouts': workouts,
        'week_count': Workout.objects.filter(completed_at__gte=timezone.now() - timedelta(days=7)).count(),
        'total_count': Workout.objects.count(),
    })


def _card(slot, state, last_log):
    lift = slot.lift
    weight = state.weight if state else None
    target = slot.high
    card = {
        'slot': slot,
        'lift': lift,
        'weight': _fmt(weight),
        'increment': _fmt(lift.increment) if lift.increment else '',
        'reps': [target] * slot.sets,
        'last': last_log,
        'last_reps': ', '.join(str(r) for r in last_log.reps) if last_log else '',
        'last_weight': _fmt(last_log.weight) if last_log else '',
        'misses': state.misses if state else 0,
        'plates': None,
    }
    if lift.equipment == 'barbell':
        card['plates'] = [_fmt(p) for p in plates_per_side(weight) or []] if weight else None
    if weight is not None and lift.increment:
        card['up_to'] = _fmt(weight + lift.increment)
    return card


@_activate_tz
def day(request, day):
    programme_day = DAYS_BY_SLUG.get(day)
    if programme_day is None:
        raise Http404

    if request.method == 'POST':
        return _complete_day(request, programme_day)

    states = _states()
    last_logs = _last_logs()
    cards = [_card(slot, states.get(slot.lift.slug), last_logs.get(slot.lift.slug)) for slot in programme_day.slots]
    last_done = Workout.objects.filter(day=programme_day.slug).first()
    return render(request, 'gym/day.html', {'day': programme_day, 'cards': cards, 'last_done': last_done,
                                            'days': DAYS})


def _complete_day(request, programme_day):
    with transaction.atomic():
        states = {s.slug: s for s in LiftState.objects.select_for_update()}
        workout = Workout.objects.create(day=programme_day.slug, completed_at=timezone.now())
        ups = []
        for slot in programme_day.slots:
            slug = slot.lift.slug
            reps = [r for r in (_parse_reps(request.POST.get(f'r-{slug}-{n}')) for n in range(slot.sets)) if r is not None]
            if not reps:
                continue  # exercise skipped
            state = states.get(slug) or LiftState(slug=slug)
            weight = None if slot.lift.timed else _parse_weight(request.POST.get(f'w-{slug}'))
            new_weight, misses, outcome = next_weight(weight, reps, slot, state.misses)
            LiftLog.objects.create(
                workout=workout, slug=slug, weight=weight, reps=reps, outcome=outcome, next_weight=new_weight,
                prev_weight=state.weight, prev_misses=state.misses,
            )
            if weight is not None:
                state.weight, state.misses = new_weight, misses
                state.save()
                states[slug] = state
            if outcome == UP:
                ups.append(f'{slot.lift.name} → {_fmt(new_weight)} kg')
            elif outcome == DELOADED:
                ups.append(f'{slot.lift.name} deload → {_fmt(new_weight)} kg')

    if ups:
        messages.success(request, f'{programme_day.short} done. Next time: ' + '; '.join(ups) + '.')
    else:
        messages.success(request, f'{programme_day.short} done. Same weights next time — chase the reps.')
    return redirect('gym:home')


@require_POST
def undo_last(request):
    """Undo the most recent workout and put every lift back where it was."""
    with transaction.atomic():
        workout = Workout.objects.select_for_update().first()
        if workout is None:
            return redirect('gym:home')
        for log in workout.logs.all():
            if log.weight is None:
                continue
            LiftState.objects.update_or_create(
                slug=log.slug, defaults={'weight': log.prev_weight, 'misses': log.prev_misses})
        label = DAYS_BY_SLUG[workout.day].short if workout.day in DAYS_BY_SLUG else workout.day
        workout.delete()
    messages.success(request, f'Undid the last {label} session.')
    return redirect('gym:home')


@_activate_tz
def lift(request, slug):
    lift_def = LIFTS.get(slug)
    if lift_def is None:
        raise Http404
    logs = list(LiftLog.objects.filter(slug=slug).select_related('workout'))
    state = LiftState.objects.filter(slug=slug).first()

    # Weight over time as an inline SVG polyline.
    points = [(log.workout.completed_at, log.weight) for log in logs if log.weight is not None]
    chart = None
    if len(points) >= 2:
        w, h, pad = 320, 120, 10
        weights = [p[1] for p in points]
        lo, hi = min(weights), max(weights)
        span = (hi - lo) or Decimal('1')
        coords = []
        for i, (_, wt) in enumerate(points):
            x = pad + (w - 2 * pad) * i / (len(points) - 1)
            y = h - pad - float((wt - lo) / span) * (h - 2 * pad)
            coords.append((round(x, 1), round(y, 1)))
        chart = {'w': w, 'h': h, 'points': ' '.join(f'{x},{y}' for x, y in coords), 'last': coords[-1],
                 'lo': _fmt(lo), 'hi': _fmt(hi)}

    rows = [{
        'log': log, 'weight': _fmt(log.weight), 'next': _fmt(log.next_weight),
        'reps': ' · '.join(str(r) for r in log.reps),
        'day': DAYS_BY_SLUG[log.workout.day].short if log.workout.day in DAYS_BY_SLUG else log.workout.day,
    } for log in reversed(logs)]
    best = max((estimated_1rm(log.weight, log.reps) or 0 for log in logs), default=0)
    return render(request, 'gym/lift.html', {
        'lift': lift_def, 'state': state, 'weight': _fmt(state.weight) if state else '',
        'rows': rows, 'chart': chart, 'best_e1rm': _fmt(best) if best else '',
        'show_e1rm': lift_def.equipment in ('barbell', 'dumbbell'),
    })


def manifest(request):
    return JsonResponse({
        'name': 'Gym',
        'short_name': 'Gym',
        'start_url': reverse('gym:home'),
        'scope': reverse('gym:home'),
        'display': 'standalone',
        'background_color': '#0b0c0a',
        'theme_color': '#0b0c0a',
        'icons': [
            {'src': static('gym/icon-192.png'), 'sizes': '192x192', 'type': 'image/png'},
            {'src': static('gym/icon-512.png'), 'sizes': '512x512', 'type': 'image/png'},
        ],
    }, content_type='application/manifest+json')
