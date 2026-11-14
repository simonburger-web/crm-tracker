"""Double progression over a rep range (e.g. 3 × 6–8).

Within a session each set's weight follows the set before it: top of the range -> one jump up; in the range
-> same weight; under the bottom -> one jump down. Next session starts at the heaviest weight that held (got
at least the bottom of the range), and one jump above that once every set at it reached the top.
"""
from .programme import BAR_KG, PLATES_KG


def next_set_weight(track, weight, reps):
    """Suggested weight for the set after one of `reps` at `weight`."""
    if weight is None or reps is None:
        return weight
    if reps >= track.high:
        return weight + track.increment
    if reps < track.low:
        return max(weight - track.increment, 0)
    return weight


def top_weight(track, sets):
    """The heaviest weight that held, or the heaviest tried if none did. `sets` is [(weight, reps)]."""
    held = [w for w, r in sets if r >= track.low]
    return max(held or [w for w, _ in sets])


def next_start(track, sets):
    """Set 1's weight for next session, from this session's logged [(weight, reps)]."""
    held = [w for w, r in sets if r >= track.low]
    if not held:
        return max(min(w for w, _ in sets) - track.increment, 0)
    top = max(held)
    if all(r >= track.high for w, r in sets if w == top):
        return top + track.increment
    return top


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
