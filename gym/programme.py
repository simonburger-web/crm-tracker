"""The training programme, defined in code: four days of single-station pairs, ~60 min each.

Weights progress per track: a lift at one rep range. A lift done at the same range on two days shares one
weight (cable lateral raise, 12–15 on days 1 and 3); at different ranges it gets one weight per range
(lat pulldown, 6–8 on day 1 and 10–12 on day 3).
"""
from dataclasses import dataclass
from decimal import Decimal

# Smallest jump each kind of kit allows. Dumbbell weights are per hand.
EQUIPMENT = {
    'barbell': {'label': 'Barbell', 'increment': Decimal('5')},
    'dumbbell': {'label': 'Dumbbells (per hand)', 'increment': Decimal('2')},
    'stack': {'label': 'Weight stack', 'increment': Decimal('2.5')},
    'plates': {'label': 'Plate-loaded', 'increment': Decimal('5')},     # 2.5 kg a side
}

KINDS = {
    'main': {'label': 'Main lift'},
    'compound': {'label': 'Compound'},
    'isolation': {'label': 'Isolation'},
}

BAR_KG = Decimal('20')
# What the gym actually has: no 25s, nothing under 2.5.
PLATES_KG = [Decimal(p) for p in ('20', '10', '5', '2.5')]


@dataclass(frozen=True)
class Lift:
    slug: str
    name: str
    equipment: str
    kind: str

    @property
    def increment(self):
        return EQUIPMENT[self.equipment]['increment']

    @property
    def equipment_label(self):
        return EQUIPMENT[self.equipment]['label']



@dataclass(frozen=True)
class Slot:
    """One exercise as it appears on a given day."""
    lift: Lift
    sets: int
    low: int
    high: int
    rest: str = ''      # shown on the solo lift, or on the last lift of a pair
    rest_seconds: int = 0
    group: str = ''     # 'A1', 'A2'… for pairs done back to back
    per_leg: bool = False

    @property
    def track(self):
        return _TRACK_BY_RANGE[(self.lift.slug, self.low, self.high)]

    @property
    def target(self):
        reps = f'{self.low}' if self.low == self.high else f'{self.low}–{self.high}'
        return f'{self.sets} × {reps}{"/leg" if self.per_leg else ""}'


def _lifts(*rows):
    return {slug: Lift(slug, name, kit, kind) for slug, name, kit, kind in rows}


LIFTS = _lifts(
    ('bench', 'Bench press', 'barbell', 'main'),
    ('incline_db_press', 'Incline DB press', 'dumbbell', 'compound'),
    ('incline_db_row', 'Incline DB row', 'dumbbell', 'compound'),
    ('cable_lateral_raise', 'Cable lateral raise', 'stack', 'isolation'),
    ('rope_pushdown', 'Rope pushdown', 'stack', 'isolation'),
    ('back_squat', 'Belt back squat', 'barbell', 'main'),
    ('rdl', 'Romanian deadlift', 'barbell', 'compound'),
    ('leg_press', 'Leg press', 'plates', 'compound'),
    ('standing_calf_raise', 'Standing calf raise', 'stack', 'isolation'),
    ('standing_leg_curl', 'Standing leg curl', 'stack', 'isolation'),
    ('ohp', 'Overhead press', 'barbell', 'main'),
    ('lat_pulldown', 'Lat pulldown', 'stack', 'compound'),
    ('seated_cable_row', 'Seated cable row', 'stack', 'compound'),
    ('cable_fly', 'Cable fly', 'stack', 'isolation'),
    ('bayesian_cable_curl', 'Bayesian cable curl', 'stack', 'isolation'),
    ('db_oh_triceps', 'Seated overhead triceps extension', 'dumbbell', 'isolation'),
    ('deadlift', 'Deadlift', 'barbell', 'main'),
    ('front_squat', 'Front squat / pause squat', 'barbell', 'compound'),
    ('bulgarian_split_squat', 'Bulgarian split squat', 'dumbbell', 'compound'),
    ('leg_extension', 'Leg extension', 'stack', 'isolation'),
)


def _s(slug, sets, low, high, rest='', rest_seconds=0, group='', per_leg=False):
    return Slot(LIFTS[slug], sets, low, high, rest, rest_seconds, group, per_leg)


@dataclass(frozen=True)
class Day:
    slug: str
    short: str
    title: str
    slots: tuple


DAYS = [
    Day('day1', 'Day 1', 'Upper — Bench', (
        _s('bench', 4, 5, 6, '3 min', 180),
        _s('lat_pulldown', 3, 6, 8, '2 min', 120),
        _s('incline_db_press', 3, 8, 12, group='A1'),
        _s('incline_db_row', 3, 8, 12, '75 s after pair', 75, 'A2'),
        _s('cable_lateral_raise', 4, 12, 15, group='B1'),
        _s('rope_pushdown', 4, 12, 15, '45 s after pair', 45, 'B2'),
    )),
    Day('day2', 'Day 2', 'Lower — Squat', (
        _s('back_squat', 4, 5, 6, '3 min', 180),
        _s('rdl', 3, 8, 8, '2 min', 120),
        _s('leg_press', 3, 10, 12, '75 s', 75),
        _s('standing_calf_raise', 3, 12, 15, '75 s', 75),
        _s('standing_leg_curl', 3, 10, 12, '45 s', 45),
    )),
    Day('day3', 'Day 3', 'Upper — Shoulders & Back', (
        _s('ohp', 4, 6, 8, '2.5 min', 150),
        _s('lat_pulldown', 3, 10, 12, '75 s', 75),
        _s('seated_cable_row', 3, 10, 12, '75 s', 75),
        _s('cable_fly', 3, 12, 15, group='B1'),
        _s('cable_lateral_raise', 3, 12, 15, '45 s after pair', 45, 'B2'),
        _s('bayesian_cable_curl', 3, 10, 12, group='C1'),
        _s('db_oh_triceps', 3, 10, 12, '45 s after pair', 45, 'C2'),
    )),
    Day('day4', 'Day 4', 'Lower — Deadlift', (
        _s('deadlift', 3, 5, 5, '3 min', 180),
        _s('front_squat', 3, 8, 8, '2 min', 120),
        _s('bulgarian_split_squat', 3, 8, 10, '60 s', 60, per_leg=True),
        _s('leg_extension', 3, 12, 15, group='A1'),
        _s('standing_calf_raise', 3, 12, 15, '45 s after pair', 45, 'A2'),
    )),
]
DAYS_BY_SLUG = {d.slug: d for d in DAYS}


@dataclass(frozen=True)
class Track:
    """One weight that progresses: a lift at one rep range."""
    key: str
    lift: Lift
    low: int
    high: int
    split: bool  # the same lift is also done at another rep range

    @property
    def name(self):
        return f'{self.lift.name} ({self.low}–{self.high})' if self.split else self.lift.name

    @property
    def increment(self):
        return self.lift.increment


def _tracks():
    ranges = {}
    for d in DAYS:
        for s in d.slots:
            seen = ranges.setdefault(s.lift.slug, [])
            if (s.low, s.high) not in seen:
                seen.append((s.low, s.high))
    tracks = {}
    for slug, lift in LIFTS.items():  # in LIFTS order; the first range keeps the plain slug (and its old weight)
        for i, (low, high) in enumerate(ranges.get(slug, [])):
            key = slug if i == 0 else f'{slug}_{low}_{high}'
            tracks[key] = Track(key, lift, low, high, len(ranges[slug]) > 1)
    return tracks


TRACKS = _tracks()
_TRACK_BY_RANGE = {(t.lift.slug, t.low, t.high): t for t in TRACKS.values()}
