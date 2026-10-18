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
from .programme import DAYS, DAYS_BY_SLUG, KINDS, LIFTS
from .progression import after_session, plates_per_side, sessions_needed

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


def _next_day(last_workout):
    """The day after the last one completed, rotating Day 1 → 2 → 3 → 4."""
    if last_workout is None:
        return DAYS[0]
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


def _progress(lift, state):
    """Where a lift stands on its way to the next automatic increase."""
    weight = state.weight if state else None
    if weight is None:
        return {'lift': lift, 'weight': '', 'set': False, 'increment': _fmt(lift.increment)}
    needed = sessions_needed(lift, weight)
    done = state.sessions
    return {
        'lift': lift, 'set': True, 'weight': _fmt(weight), 'next_weight': _fmt(weight + lift.increment),
        'increment': _fmt(lift.increment), 'done': done, 'needed': needed, 'left': needed - done,
        'dots': [i < done for i in range(needed)],
        'plates': [_fmt(p) for p in plates_per_side(weight) or []] if lift.equipment == 'barbell' else None,
    }


@_activate_tz
def home(request):
    workouts = list(Workout.objects.prefetch_related('logs')[:12])
    last_workout = workouts[0] if workouts else None
    up_next = _next_day(last_workout)
    last_by_day = {}
    for slug, completed_at in Workout.objects.values_list('day', 'completed_at'):
        last_by_day.setdefault(slug, completed_at)

    states = _states()
    lifts = [_progress(lift, states.get(lift.slug)) for lift in LIFTS.values()]
    days = [{'day': d, 'last': last_by_day.get(d.slug), 'is_next': d == up_next} for d in DAYS]
    return render(request, 'gym/home.html', {
        'days': days, 'up_next': up_next, 'lifts': lifts, 'workouts': workouts,
        'unset_count': sum(not row['set'] for row in lifts),
        'week_count': Workout.objects.filter(completed_at__gte=timezone.now() - timedelta(days=7)).count(),
        'total_count': Workout.objects.count(),
    })


@_activate_tz
def day(request, day):
    programme_day = DAYS_BY_SLUG.get(day)
    if programme_day is None:
        raise Http404

    if request.method == 'POST':
        return _complete_day(request, programme_day)

    states = _states()
    cards = [{'slot': slot, **_progress(slot.lift, states.get(slot.lift.slug))} for slot in programme_day.slots]
    last_done = Workout.objects.filter(day=programme_day.slug).first()
    return render(request, 'gym/day.html', {
        'day': programme_day, 'cards': cards, 'last_done': last_done, 'days': DAYS,
        'any_unset': any(not c['set'] for c in cards),
    })


def _complete_day(request, programme_day):
    with transaction.atomic():
        states = {s.slug: s for s in LiftState.objects.select_for_update()}
        workout = Workout.objects.create(day=programme_day.slug, completed_at=timezone.now())
        ups = []
        for slot in programme_day.slots:
            lift = slot.lift
            state = states.get(lift.slug) or LiftState(slug=lift.slug)
            prev_weight, prev_sessions = state.weight, state.sessions
            if state.weight is None:
                # First time: lock in the weight entered on the day page.
                state.weight, state.sessions = _parse_weight(request.POST.get(f'w-{lift.slug}')), 0
                if state.weight is None:
                    continue
            weight = state.weight
            state.weight, state.sessions, went_up = after_session(lift, weight, state.sessions)
            state.save()
            states[lift.slug] = state
            LiftLog.objects.create(
                workout=workout, slug=lift.slug, weight=weight, outcome='up' if went_up else 'hold',
                next_weight=state.weight, prev_weight=prev_weight, prev_sessions=prev_sessions,
            )
            if went_up:
                ups.append(f'{lift.name} {_fmt(weight)} → {_fmt(state.weight)} kg')

    if ups:
        messages.success(request, f'{programme_day.short} done. Weight goes up: ' + '; '.join(ups) + '.')
    else:
        messages.success(request, f'{programme_day.short} done. Same weights next time.')
    return redirect('gym:home')


@_activate_tz
def weights(request):
    """Manual override for the locked working weights; changing one restarts its session count."""
    states = _states()
    if request.method == 'POST':
        changed = []
        with transaction.atomic():
            for lift in LIFTS.values():
                new = _parse_weight(request.POST.get(f'w-{lift.slug}'))
                state = states.get(lift.slug) or LiftState(slug=lift.slug)
                if new is None or new == state.weight:
                    continue
                state.weight, state.sessions = new, 0
                state.save()
                changed.append(f'{lift.name} {_fmt(new)} kg')
        if changed:
            messages.success(request, 'Working weights updated: ' + '; '.join(changed) + '.')
        return redirect('gym:home')

    rows = [_progress(lift, states.get(lift.slug)) for lift in LIFTS.values()]
    return render(request, 'gym/weights.html', {'rows': rows})


@require_POST
def undo_last(request):
    """Undo the most recent workout and put every lift back where it was."""
    with transaction.atomic():
        workout = Workout.objects.select_for_update().first()
        if workout is None:
            return redirect('gym:home')
        for log in workout.logs.all():
            LiftState.objects.update_or_create(
                slug=log.slug, defaults={'weight': log.prev_weight, 'sessions': log.prev_sessions})
        label = workout.label
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
    points = [log.weight for log in logs if log.weight is not None]
    chart = None
    if len(points) >= 2:
        w, h, pad = 320, 120, 10
        lo, hi = min(points), max(points)
        span = (hi - lo) or Decimal('1')
        coords = []
        for i, wt in enumerate(points):
            x = pad + (w - 2 * pad) * i / (len(points) - 1)
            y = h - pad - float((wt - lo) / span) * (h - 2 * pad)
            coords.append((round(x, 1), round(y, 1)))
        chart = {'w': w, 'h': h, 'points': ' '.join(f'{x},{y}' for x, y in coords), 'last': coords[-1],
                 'lo': _fmt(lo), 'hi': _fmt(hi)}

    rows = [{'log': log, 'weight': _fmt(log.weight), 'next': _fmt(log.next_weight)} for log in reversed(logs)]
    return render(request, 'gym/lift.html', {
        'lift': lift_def, 'progress': _progress(lift_def, state), 'rows': rows, 'chart': chart,
        'kind_label': KINDS[lift_def.kind]['label'],
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
