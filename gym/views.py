from datetime import timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AUTO_COMPLETE, ActiveSession, LiftLog, LiftState, WeightEdit, Workout
from .programme import DAYS, DAYS_BY_SLUG, KINDS, TRACKS, Alternating
from .progression import next_set_weight, next_start, plates_per_side, top_weight

# The gym clock: "today" and workout dates are shown in local time, not the server's UTC.
GYM_TZ = ZoneInfo('Africa/Johannesburg')


def _gym_view(view):
    """Runs a view on the gym clock, after counting any session whose time is up. There's no background
    worker, so sessions are counted by whichever gym page opens next."""
    def wrapper(request, *args, **kwargs):
        with timezone.override(GYM_TZ):
            _count_finished_sessions(request)
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


def _turn(programme_day, alt, saved=None):
    """Which option of an alternating spot is on this session, and which comes after it.

    One the running session already has sets for stays put. Otherwise it's the option after the one logged
    in the last completed session of this day that logged any of them; the first option if none ever was."""
    keys = [o.track.key for o in alt.options]
    for i, key in enumerate(keys):
        if (saved or {}).get(key):
            break
    else:
        last = (LiftLog.objects.filter(workout__day=programme_day.slug, slug__in=keys)
                .order_by('-workout__completed_at', '-pk').values_list('slug', flat=True).first())
        i = (keys.index(last) + 1) % len(keys) if last else 0
    return alt.options[i], alt.options[(i + 1) % len(keys)]


def _resolve_slots(programme_day, saved=None):
    """The day's slots for this session in order: [(slot, alternating spot or None, the option after)]."""
    out = []
    for entry in programme_day.slots:
        if isinstance(entry, Alternating):
            slot, after = _turn(programme_day, entry, saved)
            out.append((slot, entry, after))
        else:
            out.append((entry, None, None))
    return out


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
    raw = (raw or '').strip()
    return int(raw) if raw.isdigit() and int(raw) <= 100 else None


def _logged(entries):
    """[(weight, reps)] for the sets with both filled in."""
    out = []
    for e in entries or []:
        weight, reps = _parse_weight((e or {}).get('w')), (e or {}).get('r')
        if weight is not None and isinstance(reps, int):
            out.append((weight, reps))
    return out


def _sets_text(entries):
    """'60×8 · 62.5×6 · 62.5×6'."""
    return ' · '.join(f'{_fmt(w)}×{r}' for w, r in _logged(entries))


def _last_logs(keys=None):
    """The latest LiftLog with sets for each track key."""
    logs = LiftLog.objects.select_related('workout').order_by('-workout__completed_at', '-pk')
    if keys is not None:
        logs = logs.filter(slug__in=keys)
    latest = {}
    for log in logs:
        if log.sets and log.slug not in latest:
            latest[log.slug] = log
    return latest


def _progress(track, state, last=None):
    """Where a track stands: the weight set 1 starts at, and what was done last time."""
    lift = track.lift
    weight = state.weight if state else None
    row = {'track': track, 'lift': lift, 'increment': _fmt(lift.increment), 'set': weight is not None,
           'weight': _fmt(weight), 'last': _sets_text(last.sets) if last else '',
           'sessions': state.sessions if state else 0}
    if weight is not None and lift.equipment == 'barbell':
        row['plates'] = [_fmt(p) for p in plates_per_side(weight) or []]
    return row


def _set_rows(slot, state, saved):
    """Each set's weight and reps for the day page. A set not yet weighed follows the set before it."""
    track = slot.track
    rows = []
    prev_w, prev_r = (state.weight if state else None), None
    for i in range(slot.sets):
        entry = (saved[i] if i < len(saved) else None) or {}
        weight, reps = _parse_weight(entry.get('w')), entry.get('r')
        chosen = weight is not None
        if not chosen:
            weight = prev_w if i == 0 else next_set_weight(track, prev_w, prev_r)
        rows.append({'n': i + 1, 'weight': _fmt(weight), 'reps': reps if reps is not None else '', 'chosen': chosen})
        prev_w, prev_r = weight, reps
    return rows


@_gym_view
def home(request):
    workouts = list(Workout.objects.prefetch_related('logs')[:12])
    last_workout = workouts[0] if workouts else None
    up_next = _next_day(last_workout)
    session = ActiveSession.objects.first()
    last_by_day = {}
    for slug, completed_at in Workout.objects.values_list('day', 'completed_at'):
        last_by_day.setdefault(slug, completed_at)

    states, last = _states(), _last_logs()
    lifts = [_progress(t, states.get(t.key), last.get(t.key)) for t in TRACKS.values()]
    days = [{'day': d, 'last': last_by_day.get(d.slug), 'is_next': d == up_next} for d in DAYS]
    return render(request, 'gym/home.html', {
        'days': days, 'up_next': up_next, 'lifts': lifts, 'workouts': workouts,
        'session': session, 'session_day': DAYS_BY_SLUG.get(session.day) if session else None,
        'unset_count': sum(not row['set'] for row in lifts),
        'week_count': Workout.objects.filter(completed_at__gte=timezone.now() - timedelta(days=7)).count(),
        'total_count': Workout.objects.count(),
    })


@_gym_view
def day(request, day):
    programme_day = DAYS_BY_SLUG.get(day)
    if programme_day is None:
        raise Http404

    if request.method == 'POST':
        return _start_day(request, programme_day)

    session = ActiveSession.objects.first()
    here = session is not None and session.day == programme_day.slug
    saved = session.sets if here else {}
    states = _states()
    resolved = _resolve_slots(programme_day, saved)
    last = _last_logs([slot.track.key for slot, _, _ in resolved])
    cards = []
    for slot, alt, after in resolved:
        key = slot.track.key
        cards.append({'slot': slot, 'key': key, 'rows': _set_rows(slot, states.get(key), saved.get(key) or []),
                      'alt': alt, 'alt_next': after,
                      **_progress(slot.track, states.get(key), last.get(key))})
    last_done = Workout.objects.filter(day=programme_day.slug).first()
    return render(request, 'gym/day.html', {
        'day': programme_day, 'cards': cards, 'last_done': last_done, 'days': DAYS,
        'any_unset': any(not c['set'] for c in cards),
        'session': session if here else None,
        'other_session_day': DAYS_BY_SLUG.get(session.day) if session and not here else None,
        'auto_minutes': int(AUTO_COMPLETE.total_seconds() // 60),
    })


def _start_day(request, programme_day):
    """Start this day, replacing any other day in progress, and keep the sets posted with it.
    An autosave only ever updates this day's running session: a page left open must not start a new one."""
    autosave = 'autosave' in request.POST
    with transaction.atomic():
        session = ActiveSession.objects.select_for_update().first()
        if session is not None and session.day != programme_day.slug:
            if not autosave:
                session.delete()
            session = None
        if session is None:
            if autosave:
                return HttpResponse(status=204)
            session = ActiveSession(day=programme_day.slug, started_at=timezone.now())
        for slot in programme_day.all_slots:
            key = slot.track.key
            names = [(f's-{key}-{i}-w', f's-{key}-{i}-r') for i in range(slot.sets)]
            if not any(w in request.POST or r in request.POST for w, r in names):
                continue
            entries = []
            for w_name, r_name in names:
                weight, reps = _parse_weight(request.POST.get(w_name)), _parse_reps(request.POST.get(r_name))
                entries.append(None if weight is None and reps is None
                               else {'w': None if weight is None else str(weight), 'r': reps})
            while entries and entries[-1] is None:
                entries.pop()
            if entries:
                session.sets[key] = entries
            else:
                session.sets.pop(key, None)
        session.save()
    if autosave:
        return HttpResponse(status=204)
    return redirect('gym:day', day=programme_day.slug)


def _count_finished_sessions(request):
    with transaction.atomic():
        cutoff = timezone.now() - AUTO_COMPLETE
        for session in ActiveSession.objects.select_for_update().filter(started_at__lte=cutoff):
            programme_day = DAYS_BY_SLUG.get(session.day)
            if programme_day is not None:
                _complete_day(request, programme_day, session)
            session.delete()


def _complete_day(request, programme_day, session):
    # Dated by when the session ran, however much later the app was next opened.
    workout = Workout.objects.create(day=programme_day.slug, completed_at=session.counts_at)
    states = {s.slug: s for s in LiftState.objects.select_for_update()}
    changes, logged_any = [], False
    for slot in programme_day.all_slots:  # every option of an alternating spot: log whichever was done
        track = slot.track
        sets = _logged(session.sets.get(track.key))
        if not sets:
            continue  # nothing logged: the weight stays as it was
        logged_any = True
        state = states.get(track.key) or LiftState(slug=track.key)
        prev_weight, prev_sessions = state.weight, state.sessions
        new = next_start(track, sets)
        base = prev_weight if prev_weight is not None else sets[0][0]
        outcome = 'up' if new > base else 'down' if new < base else 'hold'
        state.sessions = prev_sessions + 1 if new == prev_weight else 0
        state.weight = new
        state.save()
        states[track.key] = state
        LiftLog.objects.create(
            workout=workout, slug=track.key, weight=top_weight(track, sets), outcome=outcome, next_weight=new,
            sets=[{'w': str(w), 'r': r} for w, r in sets], prev_weight=prev_weight, prev_sessions=prev_sessions,
        )
        if outcome != 'hold':
            changes.append(f'{track.name} {_fmt(base)} → {_fmt(new)} kg')

    if changes:
        messages.success(request, f'{programme_day.short} counted. Next time: ' + '; '.join(changes) + '.')
    elif logged_any:
        messages.success(request, f'{programme_day.short} counted. Same weights next time.')
    else:
        messages.success(request, f'{programme_day.short} counted. No sets were logged, so weights stay the same.')


@require_POST
@_gym_view
def cancel_session(request):
    """Drop the session in progress without counting it, e.g. after tapping Start by accident."""
    ActiveSession.objects.all().delete()
    messages.success(request, 'Session cancelled. Nothing was counted.')
    return redirect('gym:home')


@_gym_view
def weights(request):
    """Manual override for the weight each track starts at next session."""
    states = _states()
    if request.method == 'POST':
        changed = []
        with transaction.atomic():
            for track in TRACKS.values():
                new = _parse_weight(request.POST.get(f'w-{track.key}'))
                state = states.get(track.key) or LiftState(slug=track.key)
                if new is None or new == state.weight:
                    continue
                if state.weight is not None:
                    last_up = LiftLog.objects.filter(slug=track.key, outcome='up').order_by('-workout__completed_at').first()
                    last_edit = WeightEdit.objects.filter(slug=track.key).first()
                    WeightEdit.objects.create(
                        slug=track.key, old_weight=state.weight, new_weight=new,
                        after_increase=bool(last_up and (not last_edit or last_up.workout.completed_at > last_edit.edited_at)),
                        sessions_at_weight=state.sessions,
                    )
                state.weight, state.sessions = new, 0
                state.save()
                changed.append(f'{track.name} {_fmt(new)} kg')
        if changed:
            messages.success(request, 'Starting weights updated: ' + '; '.join(changed) + '.')
        return redirect('gym:home')

    edits = {}
    for slug, after_increase in WeightEdit.objects.values_list('slug', 'after_increase'):
        edits[slug] = edits.get(slug, 0) + after_increase
    rows = [{**_progress(t, states.get(t.key)), 'edits_after_increase': edits.get(t.key, 0)}
            for t in TRACKS.values()]
    return render(request, 'gym/weights.html', {'rows': rows})


@require_POST
@_gym_view
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


@_gym_view
def lift(request, slug):
    track = TRACKS.get(slug)
    if track is None:
        raise Http404
    lift_def = track.lift
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

    rows = [{'log': log, 'weight': _fmt(log.weight), 'next': _fmt(log.next_weight), 'sets': _sets_text(log.sets)}
            for log in reversed(logs)]
    edits = [{'edit': e, 'old': _fmt(e.old_weight), 'new': _fmt(e.new_weight)}
             for e in WeightEdit.objects.filter(slug=slug)]
    return render(request, 'gym/lift.html', {
        'lift': lift_def, 'track': track, 'progress': _progress(track, state), 'rows': rows, 'chart': chart, 'edits': edits,
        'edits_after_increase': sum(e['edit'].after_increase for e in edits),
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
