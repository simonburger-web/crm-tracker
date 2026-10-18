"""The overload calculator: double progression, rounded to what the kit can actually load.

- Every set hits the top of the rep range -> add one increment next session.
- Inside the range -> same weight, chase more reps.
- Any set short of the bottom of the range two sessions running -> drop ~10%.
"""
from decimal import ROUND_FLOOR, Decimal

from .programme import BAR_KG, PLATES_KG

MISSES_BEFORE_DELOAD = 2
DELOAD = Decimal('0.9')

UP, HOLD, MISS, DELOADED = 'up', 'hold', 'miss', 'deload'


def round_down(weight, increment):
    return (weight / increment).to_integral_value(ROUND_FLOOR) * increment


def next_weight(weight, reps, slot, misses):
    """Return (next weight, consecutive misses, outcome) after one session of `slot` at `weight`."""
    increment = slot.lift.increment
    if increment is None or weight is None:
        return weight, 0, HOLD
    if len(reps) >= slot.sets and all(r >= slot.high for r in reps[:slot.sets]):
        return weight + increment, 0, UP
    if len(reps) < slot.sets or any(r < slot.low for r in reps):
        misses += 1
        if misses >= MISSES_BEFORE_DELOAD:
            # At least one full increment off, never below zero.
            dropped = min(round_down(weight * DELOAD, increment), weight - increment)
            return max(dropped, Decimal('0')), 0, DELOADED
        return weight, misses, MISS
    return weight, 0, HOLD


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


def estimated_1rm(weight, reps):
    """Epley estimate from the best set."""
    if not weight or not reps:
        return None
    best = max(reps)
    if best <= 0:
        return None
    return (weight * (1 + Decimal(best) / 30)).quantize(Decimal('1'))
