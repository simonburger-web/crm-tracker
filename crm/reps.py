"""Who is working, without logins: each browser picks a rep (like the old "Who are you?" picker)."""
from django.contrib.auth import get_user_model

SESSION_KEY = 'rep_id'


def active_reps():
    return get_user_model().objects.filter(is_active=True).order_by('username')


def current_rep(request):
    """The rep chosen in this browser, or None. Cached on the request."""
    if not hasattr(request, '_current_rep'):
        rep_id = request.session.get(SESSION_KEY)
        request._current_rep = active_reps().filter(pk=rep_id).first() if rep_id else None
    return request._current_rep


def reps_context(request):
    """Template context for the sidebar rep switcher (one query)."""
    reps = list(active_reps())
    rep_id = request.session.get(SESSION_KEY)
    rep = next((r for r in reps if r.pk == rep_id), None)
    if not hasattr(request, '_current_rep'):
        request._current_rep = rep
    return {'reps': reps, 'current_rep': rep}
