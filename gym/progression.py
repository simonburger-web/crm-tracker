"""The overload calculator. Working weights are locked; the app raises them, not the lifter.

Each completed session at a weight counts toward the next jump. How many sessions that takes depends on
the lift: the kit's smallest jump compared with how fast that kind of lift should climb at that weight.
"""
import math

from .programme import BAR_KG, PLATES_KG

MIN_SESSIONS = 1
MAX_SESSIONS = 8


def sessions_needed(lift, weight):
    """Sessions to complete at `weight` before adding one increment."""
    if not weight:
        return MIN_SESSIONS
    sessions = math.ceil(lift.increment / (weight * lift.rate))
    return max(MIN_SESSIONS, min(MAX_SESSIONS, sessions))


def after_session(lift, weight, sessions):
    """Count one completed session; return (weight, sessions at it, went up?)."""
    sessions += 1
    if sessions >= sessions_needed(lift, weight):
        return weight + lift.increment, 0, True
    return weight, sessions, False


def plates_per_side(total):
    """Greedy plate breakdown for a 20 kg barbell; None if the load can't be made exactly."""
    if total is None or total < BAR_KG:
        return None
    per_side = (total - BAR_KG) / 2
    plates = []
    for plate in PLATES_KG:
        while per_side >= plate:
            plates.append(plate)
            per_side -= plate
    return plates if per_side == 0 else None
